# URLEncoder và URLDecoder: mã hóa dữ liệu biểu mẫu, không phải mọi thành phần URL

Trong Java Networking, tên **URLEncoder** và **URLDecoder** rất dễ gây hiểu nhầm. Chúng không phải công cụ để “mã hóa cả URL” hoặc “giải mã mọi URI”. Hợp đồng chính của hai lớp **java.net.URLEncoder** và **java.net.URLDecoder** là xử lý dữ liệu theo quy ước **application/x-www-form-urlencoded** — định dạng thường dùng cho dữ liệu biểu mẫu HTML và cho *giá trị tham số truy vấn* ở nhiều dịch vụ web.

Nếu dùng **URLEncoder.encode(...)** cho một đường dẫn, dấu cách sẽ thành dấu cộng **+**; nhưng trong URI path thông thường, dấu cộng là một ký tự thật chứ không có nghĩa là dấu cách. Nếu gọi **URLDecoder.decode(...)** cho toàn bộ URL, dấu cộng trong path hoặc query có ngữ nghĩa khác cũng có thể bị biến thành khoảng trắng, còn những dấu phân cách đã được percent-encode có thể bị biến ngược thành ký tự cấu trúc.

Mục tiêu bài học: hiểu quy tắc form encoding, phân biệt từng thành phần URI, xây dựng và đọc query đúng cách, thấy lỗi double encoding/decoding, và chọn API phù hợp với ngữ cảnh.

## 1. URI gồm nhiều thành phần có quy tắc khác nhau

Xét địa chỉ sau:

~~~text
https://example.org/docs/a%20b?q=c%2B%2B+tips&lang=vi#overview
|https|   |example.org| |/docs/a%20b| |q=c%2B%2B+tips&lang=vi| |overview|
 scheme     authority      path                query             fragment
~~~

- **Scheme**: https — xác định loại URI/giao thức; không lấy toàn bộ chuỗi đưa vào URLEncoder.
- **Authority/host/port**: example.org — có quy tắc tên miền, IPv6, cổng và thông tin xác thực riêng.
- **Path**: /docs/a%20b — dấu **/** phân tách segment; **%20** biểu diễn byte dấu cách. Dấu **+** trong path thông thường không tự chuyển thành dấu cách.
- **Query**: q=c%2B%2B+tips&lang=vi — trong cách diễn giải *form-encoded*, **q** có giá trị “c++ tips”; dấu **&** phân tách cặp tham số và dấu **=** nối tên với giá trị. Nhưng cú pháp URI chung không bắt buộc mọi query đều theo quy tắc form này.
- **Fragment**: overview — chỉ mục phía client, thông thường không được gửi trong HTTP request target đến máy chủ.

**Percent encoding** biểu diễn byte dưới dạng **%HH** (hai chữ số hex). Với dữ liệu Unicode, các byte thường được tạo bằng **UTF-8**; ví dụ ký tự **é** trong UTF-8 là hai byte **C3 A9**, được biểu diễn **%C3%A9**. Percent encoding là cơ chế chung của URI, còn quy ước **dấu cách ↔ +** là điểm riêng của *application/x-www-form-urlencoded*.

Đừng đồng nhất: **URL** (địa chỉ tài nguyên) là một trường hợp ứng dụng của URI; **java.net.URI** hỗ trợ cấu trúc và xử lý cú pháp URI, còn **URLEncoder/URLDecoder** mang tên “URL” nhưng chủ yếu phục vụ mã hóa biểu mẫu.

## 2. Chính xác URLEncoder và URLDecoder làm gì?

Với **URLEncoder.encode(value, StandardCharsets.UTF_8)** trên Java 17:

1. Chuyển ký tự cần mã hóa thành byte theo UTF-8.
2. Giữ nguyên chữ cái ASCII, chữ số và các ký tự an toàn theo bộ quy tắc form của Java (bao gồm dấu chấm, gạch ngang, gạch dưới và dấu sao).
3. Thay dấu cách thông thường (U+0020) bằng **+**.
4. Biểu diễn những byte còn lại bằng **%HH**.

**URLDecoder.decode(encoded, StandardCharsets.UTF_8)** làm chiều ngược lại: **+** thành dấu cách, các chuỗi **%HH** thành byte rồi giải mã bằng UTF-8. Ký tự **+** vốn là dữ liệu phải được gửi thành **%2B** để phân biệt với dấu cách.

| Giá trị gốc | Form-encoded | Ý nghĩa |
|---|---|---|
| a b | a+b | Dấu cách thành + |
| a+b | a%2Bb | Dấu cộng thật được mã hóa |
| a&b=c | a%26b%3Dc | Ký tự trông giống dấu phân cách chỉ là dữ liệu |
| café | caf%C3%A9 | UTF-8 trước rồi percent-encode |
| 100% | 100%25 | Dấu % thật thành %25 |
| a/b | a%2Fb | Dấu / được mã hóa trong *giá trị form* |
| a~b | a%7Eb | Form encoder Java có bộ ký tự an toàn khác RFC 3986 |

Điểm cuối rất quan trọng: bộ ký tự an toàn của form encoder Java không giống hệt bộ ký tự **unreserved** trong RFC 3986. Chẳng hạn, dấu **~** thuộc nhóm unreserved của URI, nhưng URLEncoder có thể mã hóa nó thành **%7E**. Trong nhiều API kết quả vẫn tương đương về ý nghĩa, song chữ ký/canonicalization có thể đòi chính xác từng byte.

**Dùng overload nhận Charset** thay vì phiên bản cũ không chỉ định charset. UTF-8 phải được thống nhất giữa bên gửi và bên nhận. Việc percent-encode không tự chuẩn hóa Unicode (ví dụ ký tự có dấu được biểu diễn theo hai cách Unicode tương đương nhưng byte khác nhau); nếu giao thức yêu cầu chuẩn hóa thì làm riêng, theo hợp đồng của giao thức.

## 3. Dùng đúng cho query kiểu biểu mẫu: mã hóa từng tên và giá trị

Giả sử cần tạo request:

- Tên tham số **q** có giá trị “café + Java”.
- Hai tham số **tag** có giá trị “a&b=c” và “x y”.

Cách đúng là mã hóa **từng key và từng value**, sau đó mới ghép **=** giữa key/value và **&** giữa các cặp:

~~~text
q=caf%C3%A9+%2B+Java&tag=a%26b%3Dc&tag=x+y
~~~

**Không** mã hóa nguyên chuỗi query “q=...&tag=...”: nếu làm vậy, dấu **=** và **&** dùng để phân tách cặp cũng trở thành dữ liệu. Cũng không ghép thẳng giá trị người dùng mà không encode: một giá trị có **&** hoặc **=** sẽ bị hiểu nhầm là cấu trúc query.

### Ví dụ Java 17 đầy đủ: build và parse form query

Tệp **FormQueryDemo.java**:

~~~java
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class FormQueryDemo {
    static String pair(String key, String value) {
        return URLEncoder.encode(key, StandardCharsets.UTF_8)
                + "="
                + URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    static Map<String, List<String>> parseFormQuery(String rawQuery) {
        Map<String, List<String>> result = new LinkedHashMap<>();
        if (rawQuery == null || rawQuery.isEmpty()) {
            return result;
        }

        // Tách dấu phân cách trong chuỗi RAW trước khi decode.
        for (String field : rawQuery.split("&", -1)) {
            if (field.isEmpty()) {
                continue; // Quy ước riêng của ví dụ: bỏ cặp rỗng.
            }

            int equalIndex = field.indexOf('=');
            String rawKey = equalIndex < 0
                    ? field : field.substring(0, equalIndex);
            String rawValue = equalIndex < 0
                    ? "" : field.substring(equalIndex + 1);

            String key = URLDecoder.decode(
                    rawKey, StandardCharsets.UTF_8);
            String value = URLDecoder.decode(
                    rawValue, StandardCharsets.UTF_8);

            result.computeIfAbsent(key, ignored -> new ArrayList<>())
                    .add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        String query = String.join("&",
                pair("q", "café + Java"),
                pair("tag", "a&b=c"),
                pair("tag", "x y"));

        // Base được cố định, không có sẵn query hoặc fragment.
        URI uri = URI.create("https://example.org/search?" + query);
        Map<String, List<String>> data =
                parseFormQuery(uri.getRawQuery());

        System.out.println("URL: " + uri.toASCIIString());
        System.out.println("Raw query: " + uri.getRawQuery());
        System.out.println("q: " + data.get("q").get(0));
        System.out.println("tag 1: " + data.get("tag").get(0));
        System.out.println("tag 2: " + data.get("tag").get(1));
        System.out.println("tag count: " + data.get("tag").size());
    }
}
~~~

Chạy trong thư mục chứa tệp (Java 17+):

~~~bash
javac -encoding UTF-8 FormQueryDemo.java
java FormQueryDemo
~~~

Kết quả:

~~~text
URL: https://example.org/search?q=caf%C3%A9+%2B+Java&tag=a%26b%3Dc&tag=x+y
Raw query: q=caf%C3%A9+%2B+Java&tag=a%26b%3Dc&tag=x+y
q: café + Java
tag 1: a&b=c
tag 2: x y
tag count: 2
~~~

**Giải thích từng quyết định:**

1. **pair(...)** chỉ encode phần tên và giá trị; hai dấu phân cách được ghép ở ngoài. Nhờ vậy “a&b=c” ở dữ liệu vẫn giữ nguyên nghĩa sau decode.
2. **URI.create(...)** chỉ được dùng ở đây khi biết rõ base cố định là “https://example.org/search”, chưa có query và fragment, và phần query đã được xây dựng hợp lệ. Với URI base động có query/fragment, không được nối dấu **?** một cách mù quáng; phải dùng builder hiểu đúng từng thành phần.
3. **getRawQuery()** giữ nguyên chuỗi percent-encoded để parser tách cặp trước khi decode. Nếu dùng **getQuery()**, Java URI đã percent-decode, khiến **%26** trong giá trị xuất hiện lại như một dấu **&**. Khi đó split sẽ làm vỡ dữ liệu.
4. **split("&", -1)** tách ở dấu **&** thật của query. **indexOf('=')** chỉ dùng dấu **=** đầu tiên làm ranh giới key/value; các dấu **=** khác có thể nằm trong value. Dù ví dụ chấp nhận một field không có dấu bằng như một giá trị rỗng, API thật cần quy định rõ chính sách này.
5. **Map<String, List<String>>** giữ được các key lặp (**tag** xuất hiện hai lần). Ép về Map<String, String> sẽ dễ mất dữ liệu hoặc vô tình chọn giá trị đầu/cuối, gây lỗi logic.

Đây là parser **minh họa cho query kiểu application/x-www-form-urlencoded**. Nó có chủ đích bỏ field rỗng, không quy định canonical order, không tự đặt giới hạn kích thước, số key hoặc độ dài từng giá trị. Trong ứng dụng nhận input không tin cậy, cần giới hạn dung lượng trước khi tách/giải mã, xử lý dữ liệu sai định dạng, và tuân thủ chính sách duplicate keys của hệ thống hoặc framework.

## 4. Vì sao không decode toàn bộ URL hoặc query đã được giải mã?

Xem hai URI độc lập:

~~~text
https://example.org/files/a+b
https://example.org/search?q=a+b
~~~

- Ở **path** của URI thứ nhất, đoạn “a+b” thường có nghĩa là ký tự **a**, dấu cộng **+**, ký tự **b**. Gọi **URLDecoder.decode("a+b", UTF_8)** sẽ thành “a b” và làm thay đổi tên tài nguyên.
- Ở **query** của URI thứ hai, nếu server đã quy định query theo **form encoding**, “q=a+b” được hiểu là “a b”. Nếu giao thức dùng query RFC 3986 thông thường mà coi **+** là dấu cộng thật, tự ý dùng URLDecoder lại làm đổi dữ liệu.

Một lỗi khác liên quan đến thao tác **decode trước rồi mới split**:

~~~text
RAW query:      item=a%26b%3Dc&mode=short
decode toàn bộ: item=a&b=c&mode=short
~~~

Nếu split dòng thứ hai theo dấu **&**, parser sẽ nhầm phần giá trị **a&b=c** thành hai cặp tham số. Vì vậy khi xử lý query theo quy ước form, cần thao tác trên **getRawQuery()**, phân tích ranh giới trên chuỗi raw, rồi mới decode tên và giá trị riêng rẽ.

**URI.getQuery() không giống URLDecoder.decode(...):** **getQuery()** percent-decode các escape trong query nhưng **không** tự áp dụng quy tắc dấu **+** thành dấu cách của form. Do đó càng không nên “lấy getQuery() rồi split và decode lại” khi dữ liệu có **%26**, **%3D**, **%25**.

## 5. Encode URI path: dấu cách là %20, không phải +

**URLEncoder** không phải encoder cho một path segment. Trong path, dấu **/** là dấu ngăn segment, **?** có thể bắt đầu query, **#** bắt đầu fragment, và **+** thường là ký tự cộng. Quy tắc percent-encode của path cần biết ký tự nào là dữ liệu, ký tự nào là dấu phân cách có chủ ý.

### Ví dụ Java 17: dùng URI constructor cho path đã phân định

Tệp **UriPathDemo.java**:

~~~java
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class UriPathDemo {
    public static void main(String[] args) throws Exception {
        URI uri = new URI(
                "https", null, "example.org", -1,
                "/files/a b", null, "part 1");

        System.out.println("URI: " + uri.toASCIIString());
        System.out.println("Raw path: " + uri.getRawPath());
        System.out.println("Path: " + uri.getPath());
        System.out.println("Form value: "
                + URLEncoder.encode("a b", StandardCharsets.UTF_8));

        URI plusInPath = URI.create("https://example.org/files/a+b");
        System.out.println("Path with plus: " + plusInPath.getPath());
        System.out.println("Wrong form decode: "
                + URLDecoder.decode(
                        plusInPath.getPath(), StandardCharsets.UTF_8));
    }
}
~~~

~~~bash
javac -encoding UTF-8 UriPathDemo.java
java UriPathDemo
~~~

~~~text
URI: https://example.org/files/a%20b#part%201
Raw path: /files/a%20b
Path: /files/a b
Form value: a+b
Path with plus: /files/a+b
Wrong form decode: /files/a b
~~~

Ở đây constructor của **URI** nhận chuỗi path chưa escape và quote những ký tự cần thiết, ví dụ dấu cách thành **%20**. Nó **không phải** một hàm hiểu “segment do người dùng nhập”. Nếu dữ liệu một segment chứa dấu **/**, việc nối thẳng nó vào path khiến **/** có thể trở thành dấu phân cách segment. Lúc đó phải dùng một **path-segment encoder** hoặc URI builder có API dành riêng cho path segment, rồi kiểm tra quy tắc của server.

Đặc biệt với đường dẫn file/router, các chuỗi như **.**, **..**, dấu gạch chéo được encode (**%2F**), dấu chéo ngược và ký tự percent không được xem là an toàn chỉ vì đã escape; các proxy/router/server có thể chuẩn hóa hoặc decode ở các lớp khác nhau. Phân quyền và kiểm tra đường dẫn thực tế phải áp dụng sau khi server diễn giải tài nguyên theo quy tắc nhất quán.

**Fragment** có quy tắc encode riêng và không được gửi như một phần HTTP request target. **Host** cũng có quy tắc riêng (ví dụ xử lý tên miền quốc tế, IPv6), không phải đầu vào để đưa qua URLEncoder. **Header, cookie, JSON body** không dùng form encoder trừ khi chính giao thức đã nói rõ cần một giá trị form-encoded trong đó.

## 6. Cùng một bộ encoder có thể dùng cho body form POST

Kiểu **application/x-www-form-urlencoded** ban đầu phục vụ dữ liệu biểu mẫu, vì vậy nó còn được dùng làm **HTTP request body**. Khác biệt cốt lõi là vị trí đặt chuỗi:

- Với **GET form/query**, các cặp đã encode thường nằm sau dấu **?** của URI nếu endpoint quy định query theo kiểu form.
- Với **POST form body**, chuỗi cặp key/value đã encode nằm trong body; header **Content-Type: application/x-www-form-urlencoded; charset=UTF-8** mô tả định dạng. Charset và cách xử lý phải thống nhất với phía nhận.
- Với upload tệp hoặc nhiều phần dữ liệu, thường cần **multipart/form-data**; không dùng URLEncoder để mã hóa nội dung tệp.
- Với body JSON, dùng JSON serializer và **application/json**; không URL-encode toàn bộ JSON như một biểu mẫu nếu API không yêu cầu.

Tệp **FormBodyDemo.java** dưới đây chỉ **tạo** HttpRequest, không gọi **HttpClient.send()** nên không tạo kết nối mạng:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

public class FormBodyDemo {
    public static void main(String[] args) {
        String body = "name="
                + URLEncoder.encode("Lê An", StandardCharsets.UTF_8)
                + "&message="
                + URLEncoder.encode("a+b & c=d", StandardCharsets.UTF_8);

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("https://example.org/form"))
                .header("Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        body, StandardCharsets.UTF_8))
                .build();

        System.out.println("Body: " + body);
        System.out.println("Content-Type: "
                + request.headers().firstValue("Content-Type").orElse(""));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FormBodyDemo.java
java FormBodyDemo
~~~

~~~text
Body: name=L%C3%AA+An&message=a%2Bb+%26+c%3Dd
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
~~~

Nếu thật sự gửi request, còn cần xử lý kết quả HTTP, timeout, trạng thái lỗi, xác thực và giới hạn kích thước body. Không đặt mật khẩu, token truy cập hoặc bí mật nhạy cảm vào URL/query khi chúng có thể xuất hiện trong log, lịch sử hoặc hệ thống giám sát.

## 7. Bẫy double encoding và double decoding

**Double encoding** xảy ra khi giá trị đã percent-encoded lại được encode thêm một lần:

~~~text
Dữ liệu gốc:           a/b
Form encode 1 lần:     a%2Fb
Form encode lần 2:     a%252Fb
Decode 1 lần:         a%2Fb
Decode lần 2:         a/b
~~~

Lý do: dấu **%** của chuỗi **%2F** bị encode thành **%25**, tạo **%252F**. Nếu hệ thống có nhiều lớp tự decode theo những quy tắc khác nhau, chuỗi có thể mang ý nghĩa mới sau mỗi lần xử lý. Đây có thể là bug và có thể trở thành lỗ hổng ở router hoặc quy trình kiểm tra đường dẫn.

Ví dụ ngắn bằng Java:

~~~java
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class DoubleEncodingDemo {
    public static void main(String[] args) {
        String original = "a/b";
        String once = URLEncoder.encode(
                original, StandardCharsets.UTF_8);
        String twice = URLEncoder.encode(
                once, StandardCharsets.UTF_8);

        System.out.println("once: " + once);
        System.out.println("twice: " + twice);
        System.out.println("decode once: "
                + URLDecoder.decode(twice, StandardCharsets.UTF_8));
        System.out.println("decode twice: "
                + URLDecoder.decode(
                        URLDecoder.decode(
                                twice, StandardCharsets.UTF_8),
                        StandardCharsets.UTF_8));
    }
}
~~~

~~~bash
javac -encoding UTF-8 DoubleEncodingDemo.java
java DoubleEncodingDemo
~~~

~~~text
once: a%2Fb
twice: a%252Fb
decode once: a%2Fb
decode twice: a/b
~~~

**Quy tắc thiết kế:** xác định dữ liệu tại mỗi ranh giới là **raw** hay **already encoded**; thực hiện encode tại lúc xuất thành thành phần URI/form, decode đúng một lần tại ranh giới nhận theo giao thức. Không tự “decode cho sạch” trên mọi lớp và không trộn chuỗi đã encode với chuỗi chưa encode trong cùng một builder.

### Cẩn thận với constructor URI

**URI.create(fullEncodedUri)** phân tích chuỗi URI đã có percent-escape hợp lệ. Trong khi đó, các constructor nhiều tham số của **URI** thường nhận chuỗi thành phần **chưa quote** rồi tự quote ký tự cần thiết.

Nếu đưa kết quả **URLEncoder.encode(...)** (đã chứa ký tự **%**) vào tham số **query** của một constructor kiểu **new URI(scheme, authority, path, query, fragment)**, phần **%** có thể bị quote thêm thành **%25**. Cách làm an toàn phụ thuộc hợp đồng của builder:

- **Builder nhận giá trị thô:** truyền key/value thô để builder encode đúng thành phần một lần.
- **API nhận chuỗi raw đã encode:** truyền key/value đã encode, không để API encode lại.
- **URI.create trên chuỗi hoàn chỉnh đã được xây dựng đúng:** chỉ dùng khi kiểm soát được cấu trúc, các ký tự phân cách và sự hiện diện của query/fragment; không nối phần dữ liệu chưa tin cậy vào URI nguyên vẹn.

**Không** dùng cùng lúc hai chiến lược mà không xác định rõ builder nhận dữ liệu nào.

## 8. Validation, decoding lỗi và tính an toàn

**URLDecoder.decode(...)** có thể ném **IllegalArgumentException** nếu chuỗi escape không hợp lệ, ví dụ dấu **%** không theo sau bởi hai chữ số hex. Đối với chuỗi byte không hợp lệ theo charset đã chọn, hành vi xử lý ký tự lỗi cần được kiểm tra theo hợp đồng decoder/phiên bản Java; nếu hệ thống đòi **strict UTF-8 validation**, cần thiết kế tầng giải mã byte và **CharsetDecoder** báo lỗi rõ ràng, thay vì dựa vào việc URLDecoder luôn reject mọi trường hợp.

Ngoài ra:

1. **Giới hạn đầu vào trước khi parse:** tổng query/body size, số lượng cặp, độ dài từng key/value và số lần xuất hiện một key; nếu không, dữ liệu dài hoặc rất nhiều dấu **&** có thể tạo áp lực bộ nhớ/CPU.
2. **Chính sách duplicate keys:** với **role=user&role=admin**, tầng xác thực và tầng nghiệp vụ phải chọn cùng một chính sách; không để tầng kiểm tra chọn first-value còn tầng sử dụng chọn last-value.
3. **Không coi encoding là escaping cho mọi đầu ra:** vẫn cần HTML escaping khi đưa vào HTML, parameterized SQL cho truy vấn SQL, JSON serialization cho JSON, và kiểm tra quyền truy cập tài nguyên.
4. **Không dùng URLEncoder để kiểm tra tính hợp lệ host/URL:** user-provided scheme/host có thể tạo SSRF hoặc open redirect nếu sử dụng tùy ý; phải giới hạn origin, scheme, host/port và áp dụng quy tắc chuyển hướng phù hợp.
5. **Không tự đổi thứ tự hoặc chuẩn hóa giá trị khi có chữ ký:** API ký query có thể yêu cầu percent-encoding, thứ tự key, cách xử lý dấu cách hoặc dấu **~** khác form encoder Java. Tôn trọng chuẩn canonicalization cụ thể của API.
6. **Kiểm thử Unicode và dấu phân cách:** ký tự tiếng Việt, dấu cộng, dấu cách, **%**, **&**, **=**, **/**, chuỗi rỗng, key trùng và đầu vào không hợp lệ.
7. **Không nhầm URI parsing với validation nghiệp vụ:** tạo được một URI hợp lệ không chứng minh path an toàn, quyền truy cập hợp lệ hay endpoint được phép gọi.

## 9. Chọn API theo đúng vị trí dữ liệu

| Thành phần hoặc tác vụ | Nên dùng | Tránh |
|---|---|---|
| Một **key** hoặc **value** trong query theo quy ước form | **URLEncoder.encode(key/value, UTF_8)**; ghép dấu phân cách sau | Encode nguyên URL/query rồi mới tách |
| Parse query **form-encoded** | **getRawQuery()**, split raw key/value, **URLDecoder.decode(..., UTF_8)** riêng từng phần | **getQuery()** rồi split hoặc decode toàn chuỗi trước |
| Body **application/x-www-form-urlencoded** | Encode từng field, gửi đúng Content-Type và charset | Encode cả body một lần hoặc dùng cho file upload |
| **Path** hoặc **path segment** | **java.net.URI** với thành phần raw phù hợp, hoặc builder encode *segment* có quy ước rõ | Đưa path vào **URLEncoder** |
| **Host**, port, scheme | API/validation riêng cho authority, tên miền, IPv6 và scheme | URLEncoder cho toàn host/authority |
| **Fragment** | URI component/builder phù hợp | Hiểu fragment như dữ liệu được gửi lên HTTP server |
| Query của protocol ký/canonical riêng | Encoder và quy tắc canonicalization của protocol đó | Mặc định form encoding dùng được mọi nơi |
| JSON, XML, HTTP headers, cookie | Serializer/codec phù hợp từng định dạng | Mặc định URLEncoder cho mọi chuỗi |

## 10. Bài tập và câu hỏi tự kiểm tra

### Bài tập 1 — Phân biệt dấu cộng

Dự đoán kết quả sau mà không chạy code:

~~~java
System.out.println(URLEncoder.encode("a b", StandardCharsets.UTF_8));
System.out.println(URLEncoder.encode("a+b", StandardCharsets.UTF_8));
System.out.println(URLDecoder.decode("a+b", StandardCharsets.UTF_8));
System.out.println(URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8));
~~~

**Đáp án:**

~~~text
a+b
a%2Bb
a b
a+b
~~~

Trong ngữ cảnh một path thông thường, **a+b** vẫn là **a+b**; đừng lấy dòng thứ ba để decode path.

### Bài tập 2 — Tách query raw trước rồi mới decode

Cho raw query:

~~~text
topic=Java%26Networking&name=L%C3%AA+An&tag=a%3Db&tag=x%2By
~~~

Tự viết parser bảo toàn các key lặp. Kết quả mong đợi: **topic = Java&Networking**, **name = Lê An**, danh sách **tag = [a=b, x+y]**. Thử thay raw query bằng chuỗi đã qua **URI.getQuery()** rồi split để quan sát vì sao giá trị “Java&Networking” bị tách sai.

### Bài tập 3 — Viết bộ kiểm thử biên

Thử các giá trị: chuỗi rỗng, một dấu cộng, một dấu cách, dấu percent, Unicode có dấu, nhiều dấu **=**, hai key trùng và chuỗi **%ZZ**. Xác minh tính chất **decode(encode(x)) = x** khi cả hai phía dùng cùng UTF-8 và chuỗi đầu vào hợp lệ. Bổ sung giới hạn độ dài và số cặp trước khi parse.

### Bài tập 4 — Thiết kế URI đúng thành phần

Một người dùng đặt tên file là **report a+b.txt**. Tạo URI tới đường dẫn có một path segment mang tên này mà không biến dấu cách thành **+**, không làm mất dấu cộng thật. Sau đó thử tên file có dấu **/** hoặc **..**; giải thích vì sao còn cần quy tắc segment và kiểm tra đường dẫn, kể cả khi đã percent-encode.

### Câu hỏi thường gặp

**URLEncoder có dùng được cho tất cả query string không?** Không. Chỉ khi query được quy định hoặc hai bên thống nhất theo kiểu form. Nhiều HTTP API hiểu query theo quy ước đó, nhưng cũng có API yêu cầu RFC 3986/canonical encoding hoặc parser tùy biến.

**URLDecoder có giải mã được %20 không?** Có: với charset phù hợp, **%20** thành dấu cách. Nhưng nó còn chuyển **+** thành dấu cách, nên không dùng tùy tiện cho path hoặc mọi giá trị percent-encoded.

**Có nên gọi URLDecoder.decode(uri.toString())?** Không. Nó có thể đổi cấu trúc, path và dữ liệu đã escape. Hãy đọc từng component với API URI phù hợp, rồi decode theo đúng quy ước của component đó.

**Vì sao URI.getRawQuery() quan trọng?** Nó giữ nguyên **%26**, **%3D** và các escape để parser còn phân biệt dấu phân cách thật với byte dữ liệu. Tách ranh giới trước, decode sau.

**Đã encode là an toàn trước injection chưa?** Chưa. Encoding đúng giúp giữ cấu trúc dữ liệu tại một ranh giới cụ thể; validation, authorization, chống SSRF, output escaping và xử lý canonicalization là những trách nhiệm riêng.

**Ghi nhớ:** **URLEncoder/URLDecoder = codec của dữ liệu form theo kiểu application/x-www-form-urlencoded**. Hãy encode **key/value** riêng, chỉ decode **sau khi tách raw query**, dùng **URI/builder đúng component** cho path/fragment/authority, và tuyệt đối tránh double encoding/decoding giữa các tầng.