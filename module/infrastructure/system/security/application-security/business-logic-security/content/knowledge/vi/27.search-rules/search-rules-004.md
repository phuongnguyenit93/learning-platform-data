# Search ranking manipulation — Chống thao túng thứ hạng tìm kiếm

## 1. Khi thứ tự tìm kiếm trở thành vấn đề an ninh nghiệp vụ

Trong chương **Search Rules** của Business Logic Security, search ranking manipulation là việc tác động trái với chính sách lên dữ liệu hoặc tín hiệu xếp hạng để đưa một đối tượng lên cao, đẩy đối tượng khác xuống thấp hoặc làm người dùng ra quyết định dựa trên một thứ tự bị bóp méo.

Không phải mọi thay đổi thứ hạng đều là tấn công. Người dùng tìm đúng từ khóa, nhà cung cấp viết mô tả chính xác hơn hoặc một mặt hàng thực sự được quan tâm nhiều hơn đều có thể làm thứ tự thay đổi hợp lệ. Vấn đề xuất hiện khi một chủ thể lợi dụng quyền sửa nội dung, tham số API hay sự kiện tương tác để vượt qua giới hạn ảnh hưởng được thiết kế cho mình.

Xét một hệ thống mua hàng có danh mục thiết bị được phép đặt mua. Người dùng tìm “máy in”, còn nhà cung cấp có thể sửa tiêu đề và mô tả mặt hàng của mình. Nếu nhà cung cấp tự đặt `verified=true`, gửi `boost=1000000` hoặc phát hàng loạt click giả để chiếm vị trí đầu, kết quả tìm kiếm có thể thúc đẩy lựa chọn sai mà không cần khai thác lỗi cú pháp.

Trong module này, bảo vệ ranking phải gắn với các invariant khác: đối tượng không được phép vẫn không được xuất hiện; hàng chưa được duyệt không trở thành hàng đủ điều kiện mua; thứ hạng không cấp quyền đổi giá hoặc bỏ qua phê duyệt; gửi lại sự kiện không được tính thành nhiều bằng chứng độc lập.

## 2. Tách điều kiện được xuất hiện khỏi điểm xếp hạng

### 2.1. Hai quyết định có vai trò khác nhau

Một pipeline tìm kiếm nên phân biệt:

```text
Tập ứng viên hợp lệ E:
  đúng tenant
  AND được phép tìm/đọc theo đối tượng
  AND thỏa điều kiện nghiệp vụ của loại danh sách
  AND khớp truy vấn theo hợp đồng tìm kiếm

Thứ tự kết quả:
  xếp hạng các phần tử của E bằng policy phía server
```

Ví dụ, danh mục “đủ điều kiện đặt mua” chỉ chứa mặt hàng đã được duyệt và đang hoạt động trong phạm vi người mua được truy cập. Điểm relevance cao không thể thay thế điều kiện đó.

| Quy tắc | Loại | Cách biểu diễn phù hợp |
| --- | --- | --- |
| Đúng tenant | Điều kiện bắt buộc | Predicate giới hạn tập ứng viên |
| Có quyền đọc đối tượng | Điều kiện bắt buộc | Policy/ACL có hiệu lực |
| Đã được duyệt cho danh mục mua | Điều kiện nghiệp vụ bắt buộc trong ví dụ | Predicate trạng thái có thẩm quyền |
| Tiêu đề khớp từ khóa | Điều kiện khớp và/hoặc tín hiệu relevance theo hợp đồng | Query trên field được phép |
| Nhà cung cấp được xác minh | Tín hiệu hoặc điều kiện do sản phẩm định nghĩa | Field do luồng xác minh tin cậy quản lý |
| Mức tương tác hợp lệ | Tín hiệu mềm | Giá trị được xác thực, giới hạn ảnh hưởng |

Không dùng “cộng thêm điểm nếu đúng tenant” thay cho “chỉ lấy đúng tenant”. Cũng không dùng điểm thấp để biểu diễn từ chối quyền rồi hy vọng nó không lọt vào top kết quả.

### 2.2. Điểm không phải bằng chứng nghiệp vụ

Một kết quả đứng đầu không có nghĩa là đối tượng đã được phê duyệt, giá đã được xác nhận hoặc actor được quyền thực hiện mọi thao tác trên nó. Lệnh đặt mua hoặc duyệt sau đó phải đọc dữ liệu có thẩm quyền và kiểm tra lại tenant, action, trạng thái, phiên bản, giá và hạn mức phù hợp.

Nếu một hàng đợi kiểm soát rủi ro yêu cầu mức ưu tiên bắt buộc, đừng để văn bản do người tạo đơn sửa được quyết định toàn bộ thứ tự. Có thể cần một lớp ưu tiên nghiệp vụ do server xác định trước relevance. Khi đó phải kiểm thử lớp ưu tiên này như một invariant, thay vì chỉ theo dõi chất lượng tìm kiếm trung bình.

## 3. Lập bản đồ nguồn tín hiệu và quyền thay đổi

Trước khi sửa công thức score, xác định ai tạo và ai được thay đổi từng đầu vào:

| Đầu vào | Chủ thể có thể tác động | Rủi ro | Giới hạn cần thiết |
| --- | --- | --- | --- |
| Chuỗi tìm kiếm | Người tìm kiếm | Chèn cú pháp field/boost nếu API diễn giải quá rộng | Hợp đồng query rõ, bộ dựng query phía server |
| Tiêu đề, mô tả, tag | Chủ nội dung hoặc nhà cung cấp | Nhồi từ khóa, mạo danh nhãn đã xác minh | Giới hạn nội dung và ảnh hưởng scoring |
| `verified`, `approved`, `priorityClass` | Luồng quản trị/nghiệp vụ chuyên biệt | Tự nâng trạng thái nếu mass assignment | Kiểm tra quyền ghi từng property |
| Click, impression, lượt lưu | Trình duyệt và hệ thống ghi nhận | Replay, bot, tự tương tác | Xác thực ngữ cảnh, khử trùng, hạn mức đóng góp |
| Giao dịch đã hoàn tất | Luồng nghiệp vụ có thẩm quyền | Dùng đơn tạo thử hoặc bị hoàn làm “bằng chứng mua” | Định nghĩa sự kiện đủ điều kiện và xử lý điều chỉnh |
| Trọng số, model, sort | Cấu hình server được quản lý | Client ép policy khác hoặc tự cấp boost | Version, quyền thay đổi và cơ chế kiểm toán |

Tên field “trusted” không làm dữ liệu trở nên tin cậy. Cần biết đường ghi nào có thể cập nhật nó và đường đồng bộ nào đưa nó vào index.

Việc cho người dùng sửa các property nhạy cảm ngoài phạm vi được cấp là một dạng lỗi quyền ở mức thuộc tính, được mô tả trong [OWASP API3:2023 — Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/).

## 4. Những đường thao túng thường gặp

### 4.1. Điều khiển query DSL, field boost hoặc sort

Một API nhận chuỗi tìm kiếm nhưng chuyển nguyên một object JSON do client gửi xuống search engine có thể vô tình mở thêm `script_score`, `function_score`, tên field nội bộ hoặc cách sort không thuộc hợp đồng.

Không phải việc search engine hỗ trợ những tính năng đó là lỗi. Lỗi nằm ở việc ứng dụng trao quyền cấu hình ranking vượt quá phạm vi người dùng được phép.

Thiết kế API có thể chỉ nhận:

```json
{
  "text": "máy in",
  "category": "OFFICE_EQUIPMENT",
  "sort": "RELEVANCE",
  "pageSize": 20
}
```

Server ánh xạ `RELEVANCE`, `PRICE_ASC` hoặc các lựa chọn được hỗ trợ sang query cố định về cấu trúc. Một lựa chọn sort hợp lệ chỉ thay đổi thứ tự theo hợp đồng; nó không được bỏ điều kiện tenant, quyền hoặc trạng thái.

Nếu sản phẩm hỗ trợ cú pháp tìm kiếm nâng cao, hãy giới hạn field, operator và chi phí được phép. Không nhầm escape chuỗi SQL với kiểm soát ngữ nghĩa của một ngôn ngữ query khác. Tương tự, không coi một chuỗi được nhúng an toàn vào JSON là bằng chứng rằng mọi operator bên trong nó đều được phép sử dụng.

### 4.2. Nhồi từ khóa và làm nhiễu nội dung

Nhà cung cấp có thể lặp “máy in chính hãng đã xác minh” trong tiêu đề, mô tả hoặc hàng trăm tag. Tác động thực phụ thuộc analyzer, field, thuật toán và cấu hình ranking.

Không giả định điểm luôn tăng tuyến tính theo số lần lặp. Lucene mô tả BM25 có cơ chế bão hòa tần suất từ và chuẩn hóa độ dài tài liệu trong [Lucene — Similarity ranking models](https://lucene.apache.org/__root/docs.lucene.apache.org/core/9_12_0/core/org/apache/lucene/search/similarities/package-summary.html). Những đặc tính đó cũng không tự chứng minh hệ thống miễn nhiễm với mọi dạng thao túng nội dung.

Các giới hạn hữu ích gồm số tag, độ dài field, nội dung trùng lặp và quyền ghi các field có trọng số cao. Từ “đã xác minh” trong mô tả không được làm thay đổi field xác minh có thẩm quyền.

### 4.3. Tự ghi feature hoặc đồng bộ nhầm nguồn

Một API cập nhật nội dung cho phép body có `rankingScore`, `trustedPopularity` hoặc `priorityClass` có thể làm nhà cung cấp tự nâng điểm. Một lỗi tương tự xuất hiện ở pipeline index: nội dung nhập từ CSV ghi đè lên field do hệ thống xác minh quản lý.

Cần allowlist field được ghi theo từng operation và xác định nguồn có thẩm quyền khi merge dữ liệu. Đừng chỉ bảo vệ giao diện quản trị nếu endpoint import hoặc worker vẫn nhận cùng field từ nguồn ít tin cậy hơn.

### 4.4. Tạo tín hiệu tương tác giả

Nếu mỗi request tới `/click` đều tăng popularity, một actor có thể gửi lại cùng tương tác hoặc tạo nhiều lượt từ các tài khoản liên quan. Thứ hạng tăng có thể tiếp tục tạo thêm impression và click thật, hình thành vòng phản hồi khuếch đại tín hiệu ban đầu.

OWASP gọi việc lặp click, request hoặc submission để làm lệch số đo là **OAT-016 Skewing**. Tham khảo [OWASP Automated Threats — Skewing](https://owasp.github.io/www-project-automated-threats-to-web-applications/assets/oats/EN/OAT-016_Skewing.html).

## 5. Dựng query có điều kiện bắt buộc rõ ràng

### 5.1. Một cấu trúc dễ gây vượt phạm vi

Ví dụ sau đặt tenant vào một nhánh cộng điểm thay vì ràng buộc bắt buộc:

```json
{
  "query": {
    "bool": {
      "must": { "match_all": {} },
      "should": [
        { "term": { "tenant_id": "T-A" } },
        { "match": { "title": "máy in" } }
      ]
    }
  }
}
```

Trong Elasticsearch, khi bool query có `must` hoặc `filter`, các nhánh `should` mặc định không bắt buộc nếu không đặt điều kiện tương ứng. Cấu trúc trên không giới hạn tài liệu vào tenant A. Hành vi này được mô tả trong [Elasticsearch — Boolean query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query).

Chỉ tăng boost cho tenant A sẽ không sửa được lỗi quyền. Đối tượng tenant khác vẫn có thể nằm trong tập khớp.

### 5.2. Tách query match, filter và tín hiệu tùy chọn

Một query minh họa do server dựng cho danh mục mua hàng:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenant_id": "T-A" } },
        { "term": { "catalog_state": "ACTIVE_APPROVED" } },
        {
          "bool": {
            "should": [
              { "term": { "owner_id": "U-LAN" } },
              { "term": { "reader_ids": "U-LAN" } }
            ],
            "minimum_should_match": 1
          }
        }
      ],
      "must": [
        {
          "multi_match": {
            "query": "máy in",
            "fields": ["title^2", "public_description"]
          }
        }
      ],
      "should": [
        {
          "term": {
            "verification_status": {
              "value": "VERIFIED",
              "boost": 1.3
            }
          }
        }
      ]
    }
  }
}
```

Các ID, trạng thái và danh sách field trong ví dụ được tạo từ context/policy phía server, không sao chép tự do từ body. `reader_ids` là cách biểu diễn ACL minh họa; hệ thống thực tế có thể dùng quan hệ hoặc cơ chế quyền khác.

Nhánh owner hoặc người được chia sẻ bắt buộc có ít nhất một điều kiện đúng. Nhánh VERIFIED chỉ điều chỉnh relevance của những tài liệu đã thỏa các điều kiện bắt buộc; nó không phải bằng chứng cấp quyền.

Cần quản lý độ trễ cập nhật ACL và trạng thái trong index. Nếu source-of-truth đã thu hồi quyền nhưng `reader_ids` chưa đổi, query dựa trên index cũ vẫn có thể sai chính sách. Tùy cam kết thu hồi, dùng cập nhật đồng bộ, cơ chế version/quyền phù hợp hoặc xét lại quyền trước khi trả dữ liệu. Nếu phải lọc lại ứng viên sau tìm kiếm, metadata và phân trang cần được thiết kế tương ứng, không giả vờ một trang đã đủ.

## 6. Giới hạn ảnh hưởng của từng feature

### 6.1. Viết invariant thay vì chỉ chọn trọng số

Ví dụ các yêu cầu có thể kiểm thử:

```text
Không score nào đưa tài liệu ngoài tập được phép vào response.
Nội dung do nhà cung cấp sửa không thay đổi trạng thái xác minh.
Replay cùng một sự kiện không tăng accepted interaction lần hai.
Popularity chỉ đóng góp tối đa một phần đã định nghĩa vào soft score.
Nếu có lớp ưu tiên bắt buộc, soft score không vượt qua lớp đó.
Policy/model version do server chọn, không do client tự khai.
```

“Điểm popularity thường nhỏ” không phải một bảo đảm. Cần có miền giá trị và cách xử lý dữ liệu lỗi: âm, vượt giới hạn, không hữu hạn hoặc thiếu nguồn xác minh.

### 6.2. Không hiểu nhầm giới hạn của search engine

Elasticsearch có `function_score`, các cách gộp score và `max_boost`. Những tham số đó điều khiển cách tính điểm, không thực hiện authorization. Cũng cần hiểu `max_boost` giới hạn thành phần nào trước khi kết hợp với query score. Xem [Elasticsearch — Function score query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-function-score-query).

Một giá trị `min_score` không thay thế predicate trạng thái hoặc quyền. Nếu điểm relevance thay đổi theo query hoặc phiên bản index, cùng một đối tượng có thể đi qua ngưỡng mà không có thay đổi nghiệp vụ tương ứng.

Chuẩn hóa score về khoảng số dễ nhìn cũng không tự loại bỏ thao túng. PostgreSQL lưu ý rằng một cách chuẩn hóa rank có thể chỉ thay thang đo mà không đổi thứ tự; tài liệu cũng mô tả ảnh hưởng của tần suất, vị trí và trọng số field. Xem [PostgreSQL — Ranking Search Results](https://www.postgresql.org/docs/18/textsearch-controls.html#TEXTSEARCH-RANKING).

### 6.3. Ưu tiên bắt buộc cần ranh giới cấu trúc

Giả sử một hàng đợi nội bộ có `priorityClass` do service rủi ro xác định. Nếu lớp 2 bắt buộc đứng trên lớp 1, có thể sort theo tuple:

```text
priorityClass giảm dần
softScore giảm dần
id tăng dần để phân xử bằng nhau
```

Đây là lựa chọn của workflow đó, không phải yêu cầu mọi danh mục mua hàng phải dùng lớp ưu tiên. Nó tạo ra một ranh giới rõ hơn việc cộng một hằng số lớn vào score rồi hy vọng phần còn lại không vượt qua.

Bảo đảm này chỉ nói về thứ tự giữa các lớp trong tập đã khớp. Nó không chứng minh top 20 chứa mọi đơn cần kiểm tra, hoặc một bộ lọc tìm kiếm hẹp đã bao phủ toàn bộ nghĩa vụ kiểm soát.

## 7. Minh họa Java: soft score có giới hạn và lớp ưu tiên riêng

Đoạn mã dưới minh họa một bước rerank phía server sau khi đã xác định tập ứng viên hợp lệ. Các kiểu dữ liệu là thành phần ứng dụng cần tự hiện thực; ví dụ không thay thế query có kiểm soát quyền hoặc pipeline xác thực tín hiệu.

```java
public record RankKey(UUID id, int priorityClass, double softScore) {}

public RankKey rank(
        EligibleCandidate candidate,
        TrustedRankSignals signals,
        TrustedRankingPolicy policy) {
    if (!candidate.id().equals(signals.itemId())) {
        throw new IllegalArgumentException("Signal belongs to another item");
    }

    double rawTextScore = candidate.textScore();
    if (!Double.isFinite(rawTextScore) || rawTextScore < 0) {
        throw new InvalidRankingFeatureException();
    }
    if (signals.acceptedInteractions() < 0 || policy.interactionCap() <= 0) {
        throw new InvalidRankingFeatureException();
    }

    double text = rawTextScore / (1.0 + rawTextScore);
    double popularity = Math.min(
        signals.acceptedInteractions(), policy.interactionCap()
    ) / (double) policy.interactionCap();
    double verified = signals.verified() ? 1.0 : 0.0;

    double soft = 0.70 * text + 0.20 * popularity + 0.10 * verified;
    return new RankKey(candidate.id(), signals.priorityClass(), soft);
}

public static final Comparator<RankKey> RANK_ORDER =
    Comparator.comparingInt(RankKey::priorityClass).reversed()
        .thenComparing(
            Comparator.comparingDouble(RankKey::softScore).reversed())
        .thenComparing(RankKey::id);
```

Các hệ số và cap là ví dụ để làm rõ miền ảnh hưởng, không phải công thức relevance tối ưu. Hàm biến đổi text score là đơn điệu với đầu vào hợp lệ và giúp biểu diễn một thành phần bị giới hạn; nó không biến score thành xác suất tài liệu đúng hoặc an toàn.

Điều kiện áp dụng:

- `EligibleCandidate` chỉ được tạo trong pipeline đã kiểm tra tập ứng viên; không deserialize nguyên kiểu này từ request rồi coi là đã được cấp quyền.
- `TrustedRankSignals` phải đến từ store/pipeline được bảo vệ. Một class Java có tên Trusted không kiểm chứng dữ liệu thay cho hệ thống.
- `verified` và `priorityClass` không lấy từ mô tả, tag hoặc DTO cập nhật nội dung của nhà cung cấp.
- `interactionCap` và policy version do server quản lý. Khi thay trọng số, cần ghi version và cập nhật oracle tương ứng.
- Dữ liệu feature lỗi phải có chính sách rõ: từ chối, cách ly feature hoặc dùng fallback đã phê duyệt. Không fallback bằng cách bỏ điều kiện quyền.
- Nếu chỉ rerank một tập top-N do bước trước chọn, bảo đảm chỉ áp dụng trong tập đó. Một tài liệu bị loại trước rerank không được thuật toán phía sau tự khôi phục.

Với reranker học máy, các ranh giới vẫn cần giữ: model không được mở rộng tập được cấp quyền, feature phải có nguồn và version, dữ liệu tương tác nghi vấn không được tự động trở thành nhãn đúng chỉ vì đã được thu thập nhiều lần.

## 8. Bảo vệ pipeline tương tác và cập nhật điểm

### 8.1. Một click cần có ngữ cảnh, không chỉ item ID

Server có thể phát hành một định danh impression hoặc bằng chứng đã phục vụ kết quả, gắn actor/session phù hợp, item, loại tìm kiếm và thời hạn. Khi nhận click, kiểm tra nó thuộc ngữ cảnh được phép và chưa đóng góp vượt quy tắc.

Tuy nhiên, token impression chỉ chứng minh một response đã được tạo theo cơ chế đó; nó không chứng minh người dùng là con người độc lập hoặc thực sự quan tâm. Kẻ lạm dụng vẫn có thể tạo nhiều phiên hay nhiều lần tìm kiếm hợp lệ về mặt giao thức.

Vì vậy, cần phối hợp các điều kiện như giới hạn đóng góp theo actor–item–cửa sổ thời gian, phát hiện tự tương tác, kiểm tra nhóm tài khoản liên quan và mức tin cậy của nguồn. Rate limit chỉ theo IP hoặc request không đủ để diễn tả toàn bộ policy chống tăng điểm.

### 8.2. Khử trùng phải bền vững và nhất quán với cập nhật

Luồng ghi nhận có thể là:

```text
xác minh sự kiện và phạm vi
→ xác định event identity cùng khóa đóng góp
→ trong transaction: ghi sự kiện hợp lệ duy nhất + thay đổi cần thiết/outbox
→ commit
→ consumer cập nhật feature có khử trùng theo định danh sự kiện
```

Đặt constraint hoặc cơ chế tương đương cho định danh phải duy nhất. Hai request cùng event đến đồng thời không được cùng tăng điểm. Nếu consumer nhận lại message, nó cũng không được cộng lần hai.

Một event ID mới do client tự tạo ở mỗi lần gửi không tự đáp ứng yêu cầu “một tương tác đủ điều kiện chỉ đóng góp một lần”. Cần kiểm soát cả việc phát hành hoặc suy ra identity lẫn ngân sách đóng góp.

### 8.3. Sự kiện nghiệp vụ phải phản ánh đúng trạng thái

Nếu ranking dùng giao dịch hoàn tất, không tăng feature chỉ vì client gọi API tạo đơn. Đơn chưa thanh toán, bị hủy hoặc hoàn tiền cần được xử lý theo định nghĩa tín hiệu đã công bố.

Điều chỉnh tín hiệu nên có định danh và dấu vết để không trừ hoặc cộng lặp khi retry. Nếu feature được tính bất đồng bộ, phải biết thời điểm, cửa sổ và phiên bản dữ liệu đang được dùng; response search không nên tự cập nhật những feature nghiệp vụ có thẩm quyền chỉ vì trang được đọc lại.

Một đợt tăng tương tác có thể là nhu cầu thật. Phát hiện bất thường nên hỗ trợ điều tra và kiểm soát ảnh hưởng theo policy, không tự coi mọi tăng trưởng là gian lận.

## 9. Quyền riêng tư, field ẩn và khả năng suy luận từ score

### 9.1. Không dùng field bí mật để trả lời một truy vấn công khai tùy ý

Nếu người dùng không được đọc ghi chú kiểm soát nội bộ nhưng có thể tìm một từ trong ghi chú đó và quan sát tài liệu nhảy lên đầu, ranking có thể trở thành kênh suy luận.

Cần xác định những field nào được phép tham gia match, score, highlight, suggest và explanation cho từng loại tìm kiếm. Việc không serialize field trong `_source` chưa chứng minh nó không ảnh hưởng những đường này.

Những response chẩn đoán như explanation hoặc feature breakdown có thể chứa tên field, giá trị hay logic nội bộ. Chỉ cung cấp phần phù hợp quyền; log phục vụ điều tra cũng cần mức truy cập tương ứng.

### 9.2. Lọc tài liệu không tự cô lập mọi thống kê relevance

Elastic nêu rằng document-level security không làm thay đổi các thống kê index toàn cục dùng cho relevance; tài liệu ngoài phạm vi vẫn không được trả về nhưng score có thể dựa trên thống kê rộng hơn. Xem [Elastic — Controlling access at the document and field level](https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/controlling-access-at-document-field-level).

Vì vậy, không hứa rằng thêm hoặc sửa dữ liệu ngoài phạm vi chắc chắn không làm thay đổi score/thứ tự chỉ vì đã có filter tenant hoặc DLS. Nếu sản phẩm yêu cầu mức cô lập đó, cần đánh giá cách tách corpus, feature và kiến trúc index, cùng kiểm thử riêng.

Ẩn score số học có thể giảm một dạng quan sát nhưng không tự loại bỏ mọi suy luận qua thứ tự. Ngược lại, một thay đổi nhỏ về score không đủ để kết luận có rò rỉ nội dung cụ thể; cần một mô hình đe dọa và thí nghiệm có kiểm soát.

## 10. Cache, phân trang và cấu hình ranking

### 10.1. Cache phải giữ đúng phạm vi và policy

Cache theo mỗi text query có thể trả kết quả tenant A cho tenant B hoặc phục vụ thứ tự theo một policy không còn hiệu lực. Key và cơ chế vô hiệu hóa cần phản ánh những yếu tố làm đổi tập/kết quả: tenant, actor hoặc phạm vi quyền, query chuẩn hóa, filter, sort, policy/model version và dữ liệu tín hiệu liên quan theo thiết kế.

Đừng để một tham số client `rankingVersion=experimental` tùy ý chọn policy chỉ dành cho thử nghiệm nội bộ. Nếu có thử nghiệm A/B, server quyết định phạm vi tham gia theo cơ chế được quản lý và vẫn giữ các invariant an ninh.

### 10.2. Score thay đổi có thể làm các trang trùng hoặc thiếu

Popularity hoặc model thay đổi giữa hai trang có thể đổi thứ tự. Cursor chứa `_score` và ID không tự đóng băng toàn bộ ranking qua nhiều request.

Chọn hợp đồng rõ: danh sách live chấp nhận những biến động nào, hay một lần duyệt giữ snapshot ứng viên, feature/policy hoặc thứ tự đã tính. Nếu token gắn với một phiên ranking cụ thể, không bỏ binding đó khi hết hạn rồi âm thầm nối trang mới vào trang cũ.

Một tie-breaker giúp thứ tự xác định khi bằng điểm, nhưng không giải quyết việc điểm thay đổi. Đặc biệt, không dùng việc đi hết các trang top kết quả làm bằng chứng đã kiểm tra mọi đối tượng nghiệp vụ cần xét.

### 10.3. Thay đổi cấu hình là một đường ghi nhạy cảm

Quản lý quyền cập nhật trọng số, feature, synonym hoặc danh sách ưu tiên. Ghi nhận người thay đổi, lý do và version; chuẩn bị cách quay lại cấu hình trước khi một thay đổi gây tác động ngoài dự kiến.

Không cố giữ bí mật toàn bộ thuật toán làm biện pháp bảo vệ chính. Các giới hạn quyền ghi feature, tập ứng viên và ngân sách ảnh hưởng vẫn phải đúng khi người dùng hiểu hệ thống vận hành như thế nào.

## 11. Kiểm thử tấn công logic vào ranking

### 11.1. Tạo oracle trước khi so thứ hạng

Chuẩn bị fixture có:

- Hai tenant và nhiều actor có phạm vi đọc khác nhau.
- Mặt hàng hợp lệ, mặt hàng chưa duyệt và mặt hàng không được actor đọc.
- Nội dung khớp thật, nội dung nhồi từ khóa và nội dung giả mạo nhãn xác minh.
- Feature có nguồn kiểm chứng, sự kiện trùng và sự kiện không đủ điều kiện.
- Nếu dùng lớp ưu tiên, các item ở nhiều lớp với soft score khác nhau.

Mỗi ca âm cần positive control: cùng cách xác thực, body hợp lệ và pipeline thật nhưng dữ liệu đủ điều kiện thì search hoặc đóng góp tín hiệu hoạt động theo hợp đồng. Một response rỗng cho mọi query không chứng minh hệ thống an toàn và hữu dụng.

Không chỉ so giá trị `_score` chính xác vì score có thể phụ thuộc corpus, analyzer hoặc phiên bản engine. Ưu tiên assertion về tập được phép, quan hệ thứ tự bắt buộc, miền ảnh hưởng và trạng thái feature đã commit.

### 11.2. Ma trận kiểm thử

| Tình huống | Cách thử | Oracle |
| --- | --- | --- |
| Boost đối tượng bị cấm | Làm nội dung tài liệu tenant khác khớp mạnh | Không được trả tài liệu trái quyền |
| Điều khiển DSL | Gửi field `script_score`, `boost`, tên field nội bộ ngoài hợp đồng | Bị từ chối hoặc không có hiệu lực theo API; cấu trúc policy không đổi |
| Nhồi từ khóa | Tăng lặp từ ở field được phép sửa | Không đổi cờ xác minh/lớp ưu tiên; ảnh hưởng theo giới hạn đã định nghĩa |
| Mạo danh xác minh | Gửi text “VERIFIED” hoặc property tương ứng qua API nội dung | Không cập nhật trạng thái xác minh có thẩm quyền |
| Replay click | Cùng event nhiều lần, kể cả đồng thời | Chỉ một đóng góp hợp lệ |
| Nhiều event vượt ngân sách | Tạo nhiều lượt trong cùng phạm vi giới hạn | Accepted feature không vượt policy đóng góp |
| Consumer nhận lại | Giao lại cùng message | Feature không bị cộng/trừ lặp |
| Dữ liệu lỗi | Feature âm, quá giới hạn hoặc không hữu hạn | Xử lý lỗi/fallback đúng hợp đồng, không làm rộng quyền |
| Vượt lớp ưu tiên | Item lớp thấp có soft score tối đa | Không đứng trên lớp cao nếu policy có ranh giới đó |
| Index quyền bị trễ | Thu hồi ACL ở nguồn trước khi index cập nhật | Đáp ứng cam kết thu hồi đã chọn; không coi index cũ là quyền vĩnh viễn |
| Cache hit khác actor | Actor A làm nóng cache rồi B tìm cùng text | Không nhận tập dữ liệu hay feature giải thích của A |
| Field bí mật | Thay field không được tham gia tìm kiếm | Không ảnh hưởng theo hợp đồng field/kiến trúc đã công bố |
| Trang sau khi điểm đổi | Cập nhật popularity giữa hai request | Hành vi đúng chế độ live/snapshot, không hứa vượt khả năng |

Với case nhồi từ khóa, không đặt oracle “thứ hạng tuyệt đối không được thay đổi” nếu nội dung đó vốn là tín hiệu relevance hợp lệ. Hãy kiểm tra ranh giới: tài liệu bị cấm vẫn bị cấm, field có thẩm quyền không đổi và một tín hiệu không được vượt ảnh hưởng đã cho phép.

### 11.3. Kiểm tra cả tác động sau commit

Với replay hoặc sự kiện bất đồng bộ, đọc lại ledger, receipt, accepted contribution và feature bằng nguồn quan sát độc lập. Chỉ đếm HTTP `200` hoặc số lời gọi mock không chứng minh counter thực tế đúng.

Giữ cố định đồng hồ, policy version và fixture khi test cửa sổ thời gian. Dùng barrier/latch để điều phối request cạnh tranh; không dựa vào một khoảng sleep rồi suy ra đã có race. Khi cần, xử lý hết outbox liên quan bằng consumer kiểm soát được trước khi đối chiếu kết quả.

Khung assertion cho policy có lớp ưu tiên:

```java
assertThat(rank(lowPriority, maximumAllowedSignals, policy).softScore())
    .isBetween(0.0, 1.0);

List<RankKey> ordered = Stream.of(
        rank(lowPriority, maximumAllowedSignals, policy),
        rank(highPriority, minimumAllowedSignals, policy))
    .sorted(RANK_ORDER)
    .toList();

assertThat(ordered.get(0).id()).isEqualTo(highPriority.id());
```

Đây chỉ là một test của hàm xếp hạng. Nó cần được bổ sung bằng test query, quyền ghi feature và pipeline tương tác; không thay thế các tầng đó.

## 12. Phát hiện, điều tra và xử lý ảnh hưởng

Những quan sát hữu ích có thể gồm tốc độ tăng feature, tỷ lệ impression/click so với kết quả nghiệp vụ đủ điều kiện, số event bị khử trùng, thay đổi vị trí sau các đợt sửa nội dung và mức tập trung đóng góp của nhóm actor liên quan.

Đối với một biến động cần điều tra, ghi lại request/correlation ID, query fingerprint phù hợp chính sách dữ liệu, ranking policy version, feature version và lý do áp dụng các giới hạn. Không ghi toàn bộ truy vấn nhạy cảm, token hoặc nội dung tài liệu trái quyền chỉ để tái dựng một bảng xếp hạng.

Khi phát hiện tín hiệu bị làm giả, có thể ngừng dùng feature bị ảnh hưởng, tính lại từ ledger đã xác minh hoặc quay lại policy trước theo quy trình được quản lý. Không sửa tay score của từng tài liệu mà bỏ qua nguồn sinh sai, vì worker tiếp theo có thể tính sai trở lại.

Nếu truy vấn ranking đắt, đặt giới hạn độ dài text, số filter, fuzziness/regex/script được hỗ trợ, số ứng viên rerank và chi phí theo actor/tenant. Khống chế chi phí không được làm phát sinh fallback sang truy vấn không còn predicate quyền.

Một báo cáo lỗi tốt mô tả ranh giới bị phá, chẳng hạn:

```text
Case: REPLAYED-CLICK-PROMOTES-ITEM
Policy: ranking-v12, mỗi impression đủ điều kiện đóng góp một lần
Fixture: item I-7, actor A, impression E-9 còn hợp lệ
Action: gửi lại cùng E-9 đồng thời từ hai request
Observed: ledger một event nhưng accepted counter tăng hai lần
Impact: feature popularity không nhất quán với bằng chứng hợp lệ
Expected: một đóng góp, một cập nhật feature có thể đối soát
```

Kết luận dựa vào feature và ledger đã commit, không chỉ việc I-7 tạm thời đứng đầu một query.

## 13. Bài tập thực hành

Một hệ thống có các quy tắc hiện tại:

```text
- Search API chuyển nguyên JSON của client xuống engine.
- Tenant được đặt trong should với boost rất cao.
- Nhà cung cấp cập nhật được title, tags, verified và popularity.
- Mỗi POST /click tăng popularity thêm một đơn vị.
- Tất cả kết quả dùng score = textScore + popularity.
- Nút Đặt mua lấy giá và trạng thái từ DTO kết quả tìm kiếm.
```

Hãy thiết kế lại theo các bước:

1. Xác định tập ứng viên bắt buộc và nguồn tin cậy của từng điều kiện.
2. Thu hẹp hợp đồng request tìm kiếm, quyền sửa nội dung và quyền sửa feature.
3. Chọn cách giới hạn ảnh hưởng của popularity và bảo vệ nhãn xác minh.
4. Thiết kế định danh sự kiện, khử trùng đồng thời và ngân sách đóng góp có thể đối soát.
5. Chọn oracle cho việc nhồi từ khóa, replay và cache khác tenant.
6. Thiết kế lại lệnh đặt mua để kiểm tra dữ liệu có thẩm quyền, giá, trạng thái và quyền hiện hành.
7. Nếu có rerank hoặc phân trang nhiều bước, xác định tập nào và policy version nào được dùng ở mỗi bước.

Chống thao túng ranking hiệu quả khi hệ thống biết rõ ai có thể thay đổi từng tín hiệu, giới hạn được ảnh hưởng của tín hiệu đó và giữ cho điểm xếp hạng luôn nằm trong các ranh giới quyền cùng quy tắc nghiệp vụ đã xác định.
