# Hiển thị highlight an toàn khi nội dung có HTML

Elasticsearch highlight giúp giao diện chỉ ra phần văn bản khớp với truy vấn. Tuy nhiên, fragment do Elasticsearch trả về có thể chứa cả nội dung gốc của document và các thẻ đánh dấu do highlighter chèn vào. Nếu nội dung gốc có HTML do người dùng nhập hoặc lấy từ nguồn bên ngoài, fragment đó phải được xem là dữ liệu không tin cậy.

Một lỗi phổ biến là lấy chuỗi highlight rồi render trực tiếp bằng cơ chế chèn HTML của frontend. Cách này có thể biến thẻ hoặc thuộc tính độc hại trong nội dung được index thành mã thực thi trong trình duyệt. Việc Elasticsearch tạo ra fragment không có nghĩa fragment đã được làm sạch để hiển thị trên web.

Cách an toàn là giữ nội dung dưới dạng text, phân biệt phần khớp bằng cấu trúc dữ liệu, rồi để giao diện tạo phần tử đánh dấu bằng API render an toàn. Nếu hợp đồng bắt buộc phải trả HTML, server phải escape nội dung gốc và chỉ tự tạo những thẻ đánh dấu cố định sau khi đã tách được các đoạn highlight.

## 1. Hiểu dữ liệu highlight được tạo ra như thế nào

### 1.1. Highlight fragment gồm nội dung và thẻ đánh dấu

Giả sử document có trường mô tả:

~~~html
<p>Compact wireless keyboard for travel</p>
~~~

Người dùng tìm từ keyboard. Elasticsearch có thể trả fragment dạng:

~~~html
Compact wireless <em>keyboard</em> for travel
~~~

Thẻ em trong ví dụ được highlighter thêm vào theo cấu hình pre-tags và post-tags. Phần chữ còn lại đến từ nội dung document đã được index.

Hai nguồn dữ liệu này có mức độ tin cậy khác nhau:

- Thẻ đánh dấu do ứng dụng cấu hình có thể được kiểm soát.
- Nội dung fragment lấy từ document có thể chứa HTML, script, thuộc tính hoặc ký tự do người dùng kiểm soát.

Vì vậy, không thể coi toàn bộ chuỗi là HTML an toàn chỉ vì một phần thẻ được highlighter thêm vào.

### 1.2. Nội dung gốc có thể chứa markup độc hại

Ví dụ một document lưu nội dung:

~~~html
Wireless keyboard
<img src=x onerror="alert('xss')">
<script>alert('xss')</script>
~~~

Nếu highlighter trả về fragment có cả nội dung này, render trực tiếp fragment có thể tạo ra stored cross-site scripting (stored XSS). Payload đã được lưu trong document, sau đó xuất hiện khi một người dùng khác tìm kiếm và mở trang kết quả.

Nguồn dữ liệu có thể là:

- Nội dung do người dùng nhập.
- HTML lấy từ trang web bên ngoài.
- Nội dung import từ CMS.
- Mô tả sản phẩm từ đối tác.
- Comment hoặc tài liệu được đồng bộ từ hệ thống khác.
- Dữ liệu cũ được lập chỉ mục trước khi có quy tắc làm sạch.

Ngay cả khi form hiện tại đã validate, dữ liệu cũ hoặc dữ liệu đồng bộ vẫn có thể chứa markup không mong muốn.

### 1.3. Highlight không phải chức năng sanitize

Highlighter có nhiệm vụ tìm và đánh dấu đoạn khớp theo query. Nó không phải HTML sanitizer và không bảo đảm loại bỏ JavaScript, event handler, URL nguy hiểm hoặc thẻ không được phép.

Các tùy chọn pre-tags/post-tags chỉ xác định chuỗi dùng để đánh dấu đoạn khớp. Chúng không làm sạch phần nội dung document được chèn vào giữa các marker.

Không dùng việc Elasticsearch trả về fragment như bằng chứng rằng chuỗi đó có thể render an toàn.

## 2. Luồng xử lý an toàn

### 2.1. Giữ ranh giới giữa dữ liệu và markup

Một luồng xử lý phù hợp:

~~~mermaid
flowchart TD
    A[Document content from index] --> B[Elasticsearch highlighter]
    B --> C[Highlight fragment with markers]
    C --> D[Parse trusted marker boundaries]
    D --> E[Plain text segments]
    E --> F[API response with text and highlighted flag]
    F --> G[Frontend renders text nodes]
    G --> H[Frontend creates fixed mark element]
~~~

Backend phân tích fragment thành các đoạn text và trạng thái có highlight. Frontend nhận dữ liệu text thuần rồi tạo node hiển thị bằng framework.

Trong luồng này, nội dung từ document luôn được coi là text. Chỉ ứng dụng quyết định tạo phần tử mark.

### 2.2. Không trả raw highlight HTML cho client

Một DTO không nên chứa trường highlightHtml được lấy trực tiếp từ Elasticsearch rồi yêu cầu frontend render bằng innerHTML, dangerouslySetInnerHTML hoặc v-html.

Thay vào đó, có thể trả:

~~~json
{
  "descriptionSegments": [
    {
      "text": "Compact wireless ",
      "highlighted": false
    },
    {
      "text": "keyboard",
      "highlighted": true
    },
    {
      "text": " for travel",
      "highlighted": false
    }
  ]
}
~~~

Client chỉ cần lặp qua các segment:

- highlighted false: render text node bình thường.
- highlighted true: render text node bên trong component hoặc element đánh dấu cố định.

Không có đoạn HTML tùy ý nào từ document được thực thi.

### 2.3. Chọn một định dạng response thống nhất

Nếu API có nhiều loại nội dung, có thể định nghĩa kiểu segment dùng chung:

~~~java
public record TextSegment(
    String text,
    boolean highlighted
) {
}

public record HighlightedField(
    String field,
    List<TextSegment> segments
) {
}
~~~

DTO kết quả:

~~~java
public record SearchResultItem(
    String id,
    String title,
    List<HighlightedField> highlights
) {
}
~~~

Cấu trúc này thể hiện rõ text là dữ liệu và highlighted chỉ là trạng thái trình bày. Client không phải phân tích HTML hoặc đoán thẻ nào do server tạo.

## 3. Cấu hình highlighter trong Elasticsearch

### 3.1. Dùng pre-tags và post-tags cố định

Trong query DSL, highlighter thường được cấu hình như sau:

~~~json
{
  "query": {
    "match": {
      "description": "wireless keyboard"
    }
  },
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "description": {}
    }
  }
}
~~~

Ví dụ trên minh họa request Elasticsearch đầy đủ, gồm query và highlight. Với Spring Data StringQuery, cần nhớ StringQuery thường biểu diễn query clause; phần highlight được gắn qua API phù hợp của phiên bản Spring Data Elasticsearch hoặc native search request.

Các thẻ pre/post nên là giá trị cố định do server cấu hình. Không lấy chúng trực tiếp từ query parameter của người dùng.

### 3.2. Ví dụ Spring Data Elasticsearch

Với NativeQuery, có thể cấu hình highlight qua builder của Elasticsearch Java API Client. Cú pháp cụ thể phụ thuộc phiên bản Spring Data Elasticsearch và client:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("description")
        .query(keyword)
    ))
    .withHighlightQuery(h -> h.fields(
        "description",
        field -> field
            .preTags("<mark>")
            .postTags("</mark>")
    ))
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

Đây là ví dụ định hướng API. Tên overload, kiểu builder và vị trí cấu hình pre/post tags có thể khác giữa các phiên bản. Hãy dùng API của dependency thực tế trong dự án.

### 3.3. Đọc fragment từ SearchHit

Spring Data cung cấp highlight field trên từng hit:

~~~java
for (SearchHit<ProductDocument> hit : hits) {
    List<String> fragments =
        hit.getHighlightField("description");

    // Chuyển fragment thành cấu trúc an toàn trước khi trả DTO.
}
~~~

Một field có thể có nhiều fragment. Không nên giả định danh sách chỉ có một phần tử hoặc fragment luôn tồn tại.

Nếu field không có nội dung phù hợp, query không yêu cầu highlight hoặc highlighter không tạo fragment, danh sách có thể rỗng.

### 3.4. Giới hạn field và fragment

Chỉ yêu cầu highlight cho field được giao diện sử dụng. Có thể giới hạn số fragment và kích thước fragment bằng tùy chọn highlighter phù hợp.

Điều này giúp:

- Giảm kích thước response.
- Tránh tạo fragment quá dài.
- Giảm chi phí xử lý highlight.
- Hạn chế lượng nội dung không cần thiết gửi tới client.

Highlight không nên được bật trên mọi field trong mọi endpoint chỉ vì tính năng có sẵn.

## 4. Phương án ưu tiên: marker riêng và structured segments

### 4.1. Vì sao không dùng thẻ HTML làm marker?

Nếu highlighter chèn em và backend cố parse HTML để giữ lại mọi thẻ em, nội dung gốc cũng có thể chứa em do người dùng nhập. Khi đó backend khó phân biệt thẻ nào do highlighter tạo và thẻ nào thuộc document.

Một hướng rõ ràng hơn là dùng marker không phải HTML, chẳng hạn:

~~~text
__HL_START_7F31A9__
__HL_END_7F31A9__
~~~

Highlighter chèn hai marker này quanh đoạn khớp. Sau đó backend tách chuỗi theo marker, coi mọi nội dung nằm giữa các marker là text thuần và trả về segments.

Marker nên được sinh ở server, có nonce ngẫu nhiên đủ dài theo từng request hoặc lần thực thi, không lấy từ client. Điều này làm giảm khả năng nội dung nguồn vô tình hoặc cố ý chứa marker giống hệt. Backend cũng cần kiểm tra marker xuất hiện đúng cặp và đúng thứ tự; nếu cấu trúc không hợp lệ, fallback về hiển thị plain text thay vì cố đoán markup.

### 4.2. Ví dụ fragment có marker

Giả sử highlighter trả:

~~~text
Compact wireless __HL_START_7F31A9__keyboard__HL_END_7F31A9__ for travel
~~~

Backend có thể phân tích thành:

~~~json
[
  {
    "text": "Compact wireless ",
    "highlighted": false
  },
  {
    "text": "keyboard",
    "highlighted": true
  },
  {
    "text": " for travel",
    "highlighted": false
  }
]
~~~

Nội dung không được parse như HTML. Nếu document gốc chứa img onerror, chuỗi đó vẫn chỉ là giá trị text trong một segment.

### 4.3. Tạo marker cho mỗi request

Ví dụ Java dùng token ngẫu nhiên:

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

public final class HighlightMarkers {

    private static final SecureRandom RANDOM = new SecureRandom();

    private final String start;
    private final String end;

    private HighlightMarkers(String token) {
        this.start = "__HL_START_" + token + "__";
        this.end = "__HL_END_" + token + "__";
    }

    public static HighlightMarkers create() {
        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);

        String token = HexFormat.of().formatHex(bytes);
        return new HighlightMarkers(token);
    }

    public String start() {
        return start;
    }

    public String end() {
        return end;
    }
}
~~~

Token 128-bit giúp marker khó bị trùng với nội dung tự nhiên. Nếu cần dùng marker trong highlighter request, truyền chúng qua cấu hình pre/post tags của request. Không ghi marker cố định có thể đoán được vào tài nguyên công khai.

Nếu hệ thống không thể cấu hình marker theo request, có thể dùng marker cố định khó trùng và kiểm tra collision với dữ liệu đã chuẩn hóa. Tuy nhiên marker ngẫu nhiên theo request tạo ranh giới tốt hơn.

### 4.4. Parse fragment thành segments

Ví dụ parser đơn giản cho một cặp marker không lồng nhau:

~~~java
public List<TextSegment> parseSegments(
        String fragment,
        String start,
        String end) {

    List<TextSegment> segments = new ArrayList<>();
    int position = 0;

    while (position < fragment.length()) {
        int startIndex = fragment.indexOf(start, position);

        if (startIndex < 0) {
            addPlainText(segments, fragment.substring(position));
            break;
        }

        if (startIndex > position) {
            addPlainText(
                segments,
                fragment.substring(position, startIndex)
            );
        }

        int textStart = startIndex + start.length();
        int endIndex = fragment.indexOf(end, textStart);

        if (endIndex < 0) {
            // Marker không đầy đủ: không tạo markup từ phần còn lại.
            addPlainText(segments, fragment.substring(startIndex));
            break;
        }

        String highlightedText =
            fragment.substring(textStart, endIndex);

        if (!highlightedText.isEmpty()) {
            segments.add(new TextSegment(highlightedText, true));
        }

        position = endIndex + end.length();
    }

    return List.copyOf(segments);
}

private void addPlainText(
        List<TextSegment> segments,
        String text) {

    if (!text.isEmpty()) {
        segments.add(new TextSegment(text, false));
    }
}
~~~

Đây là parser minh họa cho marker không lồng nhau. Bản production nên kiểm tra thêm:

- Marker start/end có đúng cặp và không bị lồng.
- Số marker không vượt giới hạn hợp lý.
- Fragment không vượt giới hạn độ dài.
- Marker không bị thiếu hoặc xuất hiện sai thứ tự.
- Khi parser gặp dữ liệu bất thường, fallback sang plain text.
- Marker được tạo theo request và không bị client kiểm soát.

Không dùng parser này để xử lý HTML tổng quát. Nó chỉ nhận diện marker do ứng dụng cấu hình.

### 4.5. Xử lý nội dung chứa marker

Marker ngẫu nhiên làm xác suất trùng rất thấp nhưng không nên bỏ qua kiểm tra cấu trúc. Nếu nội dung nguồn có chứa đúng marker, parser có thể phân đoạn sai.

Có thể chọn một nonce mới khi phát hiện marker xuất hiện trong nội dung gốc nếu ứng dụng có thể kiểm tra, hoặc coi fragment có cấu trúc marker bất thường là plain text. Không cố sửa fragment bằng cách xóa các marker không khớp.

## 5. Render structured segments ở frontend

### 5.1. React

Với React, render text qua JSX và tạo element cố định cho đoạn highlight:

~~~jsx
function HighlightedText({ segments }) {
  return (
    <>
      {segments.map((segment, index) =>
        segment.highlighted
          ? <mark key={index}>{segment.text}</mark>
          : <span key={index}>{segment.text}</span>
      )}
    </>
  );
}
~~~

React escape text children mặc định. Giá trị segment.text được hiển thị như text, không được diễn giải thành HTML.

Không thay đoạn này bằng dangerouslySetInnerHTML với raw fragment từ Elasticsearch.

### 5.2. Vue

Với Vue, dùng interpolation và element có điều kiện:

~~~vue
<template>
  <span>
    <template v-for="(segment, index) in segments" :key="index">
      <mark v-if="segment.highlighted">{{ segment.text }}</mark>
      <span v-else>{{ segment.text }}</span>
    </template>
  </span>
</template>
~~~

Interpolation của Vue escape nội dung text. Tránh v-html="fragment" với fragment chưa được làm sạch.

### 5.3. JavaScript DOM API

Nếu giao diện dùng JavaScript thuần, tạo text node và element:

~~~javascript
function appendSegments(container, segments) {
  for (const segment of segments) {
    if (segment.highlighted) {
      const mark = document.createElement("mark");
      mark.textContent = segment.text;
      container.appendChild(mark);
    } else {
      container.appendChild(
        document.createTextNode(segment.text)
      );
    }
  }
}
~~~

Dùng textContent hoặc createTextNode để nội dung luôn được xem là text. Không nối segment.text vào innerHTML.

### 5.4. Vì sao text node an toàn hơn HTML string?

Trình duyệt phân biệt text node và markup:

- Text node hiển thị ký tự <, > và dấu ngoặc kép như nội dung.
- HTML string được parser diễn giải thành element, attribute và nội dung.
- Event handler trong attribute hoặc thẻ script có thể thực thi khi được chèn vào DOM.

Vì vậy, khi chỉ cần in đậm/tô màu một phần văn bản, structured segments là mô hình phù hợp hơn việc gửi HTML tùy ý qua API.

## 6. Nếu bắt buộc phải trả HTML

Có một số hệ thống legacy yêu cầu trường HTML fragment vì nhiều client cùng dùng. Trong trường hợp đó, server phải tự tạo HTML từ các segment đã phân tích.

### 6.1. Escape text trước khi bọc thẻ

Quy trình:

1. Parse fragment thành các segment theo marker tin cậy.
2. Escape toàn bộ text segment theo ngữ cảnh HTML text.
3. Tự bọc segment highlight bằng một thẻ cố định như mark.
4. Không giữ lại bất kỳ tag hoặc attribute nào từ nội dung gốc.
5. Chỉ trả chuỗi HTML do server tạo từ các phần đã xử lý.

Ví dụ khái niệm:

~~~java
String toSafeHtml(List<TextSegment> segments) {
    StringBuilder html = new StringBuilder();

    for (TextSegment segment : segments) {
        String escaped = Encode.forHtml(segment.text());

        if (segment.highlighted()) {
            html.append("<mark>")
                .append(escaped)
                .append("</mark>");
        } else {
            html.append(escaped);
        }
    }

    return html.toString();
}
~~~

Encode.forHtml là API ví dụ từ OWASP Java Encoder. Có thể dùng thư viện encoding phù hợp của dự án, nhưng phải chọn đúng encoder cho ngữ cảnh HTML text.

Kết quả chỉ có thẻ mark do server tạo. Nội dung như img onerror sẽ được escape thành ký tự hiển thị, không thành element.

### 6.2. Không dùng escape HTML cho mọi ngữ cảnh

HTML encoding phụ thuộc vị trí chèn:

| Ngữ cảnh | Cách xử lý |
|---|---|
| Nội dung text giữa các thẻ | HTML text encoding |
| Giá trị attribute | Attribute encoding |
| JavaScript string | JavaScript encoding hoặc tránh nhúng trực tiếp |
| URL | Validate scheme/host và URL encode đúng thành phần |
| CSS value | Tránh đưa dữ liệu không tin cậy vào CSS; nếu bắt buộc phải dùng encoder phù hợp |

Một chuỗi đã được escape cho HTML text không tự động an toàn khi đặt trong attribute, JavaScript hoặc URL.

Tốt nhất là không đưa highlight content vào các ngữ cảnh đó. Nếu cần hiển thị nội dung, dùng text node.

### 6.3. Không tin vào sanitizer cấu hình quá rộng

Nếu phải nhận HTML có định dạng, dùng sanitizer với allowlist thẻ và attribute tối thiểu. Ví dụ chỉ cho phép một số tag văn bản như strong, em, mark, p, br và loại bỏ:

- script, iframe, object, embed.
- Event handler như onclick, onerror.
- URL scheme nguy hiểm như javascript:.
- Attribute hoặc namespace không cần thiết.
- CSS tùy ý nếu không có yêu cầu rõ ràng.

Sanitizer cần được cấu hình và cập nhật theo thư viện đáng tin cậy. Không tự viết sanitizer bằng regex.

Tuy nhiên, sanitizer chỉ giữ các tag được allowlist; nó không biết tag em nào do highlighter tạo và tag nào đến từ nội dung gốc. Nếu chỉ muốn đánh dấu chính xác phần khớp, marker riêng và structured segments vẫn dễ kiểm soát hơn.

### 6.4. Jsoup Safelist

Nếu sản phẩm thực sự cần giữ một tập HTML định dạng, có thể cân nhắc Jsoup với Safelist chặt:

~~~java
String safeHtml = Jsoup.clean(
    untrustedHtml,
    Safelist.basic()
);
~~~

Đây chỉ là ví dụ API. Safelist.basic() cho phép một số markup phổ biến và có thể rộng hơn nhu cầu của trường highlight. Hãy xây Safelist riêng, chỉ giữ tag và attribute mà sản phẩm cần, rồi kiểm thử với payload thực tế.

Không dùng Safelist.relaxed() hoặc allowlist rộng hơn chỉ để giữ nguyên HTML đầu vào mà chưa đánh giá rủi ro.

## 7. Nội dung HTML được index và analyzer

### 7.1. Quyết định index HTML hay text đã làm sạch

Nếu trường dữ liệu là HTML, cần xác định mục đích tìm kiếm:

- Tìm trong nội dung hiển thị sau khi bỏ markup.
- Tìm cả nội dung attribute hoặc metadata.
- Giữ nguyên HTML để hiển thị lại.
- Chỉ tìm title/heading hoặc một vùng nội dung cụ thể.

Với tìm kiếm văn bản thông thường, thường nên index phần text đã được trích xuất hoặc làm sạch theo quy tắc nghiệp vụ. Nội dung HTML gốc có thể được lưu ở nơi phù hợp để render qua pipeline sanitize riêng.

### 7.2. HTML strip char filter

Elasticsearch có HTML strip char filter để loại tag HTML trước khi phân tích text. Ví dụ mapping analyzer có thể dùng char filter html_strip.

Cấu hình khái niệm:

~~~json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "html_text": {
          "type": "custom",
          "char_filter": ["html_strip"],
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "analyzer": "html_text"
      }
    }
  }
}
~~~

Cách này giúp analyzer bỏ tag khi tạo term. Nó không phải HTML sanitizer cho nội dung được trả về và không thay thế việc encode khi render giao diện.

### 7.3. Lưu riêng source gốc và nội dung search

Một mô hình có thể dùng hai trường hoặc hai nguồn dữ liệu:

- Nội dung gốc để hiển thị sau khi sanitize.
- Nội dung text đã chuẩn hóa để tìm kiếm và highlight.

Cần đồng bộ hai bản khi cập nhật document. Nếu highlight được tạo từ field text sạch, fragment thường dễ xử lý hơn, nhưng vẫn phải xem là dữ liệu text không tin cậy.

Không giả định html_strip loại bỏ mọi dạng nội dung nguy hiểm khỏi _source. Analyzer chỉ tác động đến quá trình lập chỉ mục/tìm kiếm.

### 7.4. Đừng dùng highlighter như HTML renderer

Highlighter không tái tạo một DOM an toàn. Nó tạo fragment văn bản dựa trên nội dung đã index và các marker. Vì vậy, không dùng fragment để khôi phục trang HTML đầy đủ hoặc giữ nguyên cấu trúc HTML gốc.

Nếu cần render rich text, hãy lấy nội dung qua pipeline render/sanitize chuyên biệt, còn highlight chỉ là một tín hiệu đánh dấu văn bản.

## 8. Các loại highlighter và lưu ý hiển thị

Elasticsearch có nhiều highlighter, chẳng hạn unified, plain và postings. Mỗi loại có cách tạo fragment và yêu cầu dữ liệu riêng.

Dù chọn loại nào, nguyên tắc bảo mật không đổi:

- Fragment có thể chứa nội dung nguồn.
- Pre/post tags không làm sạch nội dung.
- Fragment có thể được cắt ở ranh giới khác nhau tùy highlighter.
- Một kết quả có thể có nhiều fragment.
- Nội dung HTML gốc có thể xuất hiện trong fragment.
- Phải xử lý text an toàn trước khi đưa ra trình duyệt.

Không dựa vào việc một highlighter cụ thể thường trả plain text để bỏ qua escaping. Mapping, dữ liệu và cách index có thể thay đổi theo thời gian.

## 9. Kiểm thử XSS và tính đúng của highlight

### 9.1. Tạo fixture có payload HTML

Dữ liệu kiểm thử nên có cả nội dung bình thường và payload:

~~~html
Wireless keyboard for travel
<img src=x onerror="alert(1)">
<script>alert(2)</script>
<a href="javascript:alert(3)">click</a>
<em>user supplied emphasis</em>
~~~

Chạy query để tạo fragment có highlight nằm trước, giữa và sau các payload.

### 9.2. Kiểm tra structured segments

Unit test cho parser nên xác nhận:

- Text gốc được giữ nguyên.
- Chỉ đoạn nằm giữa marker được đánh dấu.
- Không có marker thừa trong response.
- Marker thiếu cặp khiến parser fallback an toàn.
- Fragment không có marker được trả thành một segment plain text.
- Nhiều cặp marker được xử lý theo quy tắc đã định.
- Payload HTML vẫn nằm trong thuộc tính text.

Ví dụ kỳ vọng: chuỗi img src=x onerror="alert(1)" xuất hiện nguyên văn trong segment.text, không được chuyển thành element.

### 9.3. Kiểm tra HTML output nếu API phải trả HTML

Nếu server tạo HTML từ segments, kiểm tra:

- script trong input trở thành text đã escape.
- onerror, onclick không xuất hiện thành attribute hoạt động.
- URL javascript: không được tạo.
- Chỉ có tag mark do server tạo.
- Dấu ngoặc kép, dấu nháy đơn, ampersand và ký tự Unicode được giữ đúng.
- Fragment lỗi marker không sinh markup ngoài dự kiến.

Test không nên chỉ tìm chuỗi script trong output; cần kiểm tra DOM đã parse để chắc chắn không có script hoặc event handler hoạt động.

### 9.4. Kiểm thử ở trình duyệt

Integration/E2E test có thể:

1. Tạo document chứa payload XSS.
2. Index document vào Elasticsearch.
3. Gọi endpoint search.
4. Mở trang kết quả trong trình duyệt test.
5. Xác nhận nội dung được hiển thị như text.
6. Xác nhận không có event handler hoặc script thực thi.
7. Xác nhận phần khớp vẫn được đánh dấu đúng.
8. Kiểm tra nhiều fragment và nội dung HTML bất thường.

Đừng chỉ kiểm thử API JSON. Một DTO có thể an toàn ở backend nhưng frontend vẫn dùng innerHTML sai cách.

### 9.5. Kiểm tra thư viện và dependency

Nếu dùng sanitizer, hãy giữ dependency ở phiên bản được cập nhật và theo dõi advisory bảo mật. Không dùng thư viện parser HTML cũ hoặc regex tự viết để làm sạch markup.

## 10. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Script chạy khi mở trang kết quả | Raw highlight fragment được render bằng innerHTML | Trả structured segments và render text node |
| img onerror xuất hiện thành ảnh | Nội dung source được hiểu là HTML | Escape text hoặc sanitize bằng allowlist |
| Tag em do người dùng nhập cũng được giữ | Backend chỉ whitelist tag mà không phân biệt nguồn | Dùng marker riêng cho highlighter |
| Highlight bị mất sau khi escape | Escape toàn bộ fragment chứa cả marker | Parse marker trước, sau đó encode từng text segment |
| JSON chứa lt mark gt nhưng client không tô sáng | Double encoding hoặc API đang trả text đã escape | Chọn một tầng chịu trách nhiệm encoding |
| Marker xuất hiện trong kết quả | Parser không xử lý marker thiếu cặp hoặc bị lỗi | Validate cặp marker và fallback plain text |
| Nội dung có dấu ngoặc kép làm hỏng HTML | Nối chuỗi HTML thủ công | Dùng encoder theo ngữ cảnh hoặc DOM text node |
| Sanitizer xóa cả phần highlight | Allowlist không giữ tag hoặc pipeline sanitize sai thứ tự | Parse marker thành segment rồi tạo mark element |
| Highlight khác với nội dung hiển thị | Search field và display field không đồng nhất | Xác định nguồn text và mapping dùng cho highlight |
| Fragment quá dài hoặc response nặng | Không giới hạn fragment/field | Giới hạn số fragment và kích thước |
| XSS chỉ xuất hiện với dữ liệu import | Dữ liệu cũ/ngoài hệ thống không qua validation hiện tại | Coi mọi nội dung index là không tin cậy |

## 11. Quy trình triển khai đề xuất

Một luồng triển khai thực tế:

1. Xác định field nào cần highlight và nội dung field có thể chứa HTML hay không.
2. Cấu hình highlighter với marker do server kiểm soát.
3. Đọc fragment từ SearchHit.
4. Kiểm tra marker và parse thành các segment text.
5. Nếu marker lỗi hoặc thiếu, fallback về plain text.
6. Trả DTO có text và highlighted, không trả raw HTML.
7. Frontend render text bằng interpolation/JSX/text node và tạo phần tử mark cố định.
8. Nếu bắt buộc trả HTML, escape từng segment trước khi server tự bọc tag.
9. Thêm test cho payload XSS, ký tự đặc biệt, Unicode và marker bất thường.
10. Chạy E2E test để xác nhận trình duyệt không thực thi nội dung từ document.
11. Giới hạn field, fragment và kích thước response.
12. Theo dõi thay đổi highlighter/mapping và kiểm thử lại khi nâng phiên bản Elasticsearch.

Nếu hệ thống đã có API trả raw highlight HTML, hãy chuyển dần sang structured segments và cập nhật client trước khi loại bỏ field cũ. Không giữ hai cách render song song mà không xác định rõ field nào được phép dùng.

## 12. Những điểm cần ghi nhớ

- Highlight fragment có cả marker do highlighter tạo và nội dung document; toàn bộ fragment phải được coi là không tin cậy.
- Elasticsearch highlight không phải HTML sanitizer.
- Không render raw fragment bằng innerHTML, dangerouslySetInnerHTML hoặc v-html.
- Cách ưu tiên là dùng marker riêng, parse thành structured segments rồi render text node và phần tử mark cố định.
- Marker nên do server sinh, khó đoán, được kiểm tra cặp và có fallback plain text khi bất thường.
- Nếu bắt buộc trả HTML, escape từng đoạn text theo đúng ngữ cảnh rồi chỉ tự tạo thẻ đánh dấu cố định.
- Sanitizer phải dùng allowlist tối thiểu; regex không phải HTML sanitizer.
- html_strip char filter giúp xử lý text khi index, nhưng không làm sạch nội dung trả về cho trình duyệt.
- Highlight có thể có nhiều fragment và tốn tài nguyên; chỉ yêu cầu field cần dùng và giới hạn số lượng.
- Kiểm thử payload XSS cả ở parser, API response và trình duyệt.
- Mọi nội dung do người dùng hoặc hệ thống bên ngoài cung cấp đều cần được xem là không tin cậy, kể cả khi đã được lưu trong Elasticsearch.

Khi giữ ranh giới rõ ràng giữa text và markup, ứng dụng vẫn có thể làm nổi bật từ khóa trong kết quả tìm kiếm mà không biến nội dung HTML được index thành mã có thể thực thi trong trình duyệt.
