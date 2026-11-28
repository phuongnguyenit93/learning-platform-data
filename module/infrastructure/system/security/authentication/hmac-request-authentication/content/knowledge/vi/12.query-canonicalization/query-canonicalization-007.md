# Dấu phân cách

Trong HTTP URL, **dấu phân cách** quyết định ranh giới giữa **path** và **query**, giữa **các tham số query**, cũng như giữa **tên tham số** và **giá trị**. Những ký tự nhỏ như `?`, `&` và `=` ảnh hưởng trực tiếp đến ý nghĩa của request. Khi ký HTTP request bằng HMAC, client và server phải thống nhất không chỉ danh sách tham số mà cả **cách nhận biết ranh giới và tạo canonical query bytes**.

Ví dụ hai request:

~~~http
GET /v1/orders?status=open&limit=10 HTTP/1.1
GET /v1/orders?status=open%26limit%3D10 HTTP/1.1
~~~

Không được mặc định chúng tương đương. Request thứ nhất có thể chứa **hai tham số**, còn request thứ hai có thể chứa **một giá trị tham số** chứa các ký tự đã percent-encode, nếu protocol cho phép và decode đúng. Nếu signer và verifier phân tách query khác với router, một chữ ký hợp lệ có thể bảo vệ **một cách hiểu** trong khi business handler thực thi **cách hiểu khác**.

Bài học thuộc chương **Query canonicalization** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun thiết kế xác thực HTTP request bằng shared secret và HMAC trên canonical request gồm method, URI, header hoặc body theo hợp đồng ký; vì vậy quy tắc dấu phân cách query cần kết hợp với timestamp/nonce chống replay, key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền.

> **Nguyên tắc trung tâm:** Parser query và canonicalizer phải thống nhất với nhau và với handler về **bao nhiêu tham số tồn tại, tên/giá trị từng tham số là gì và tham số nào ảnh hưởng đến thao tác**. Không đủ để hai phía cùng dùng thuật toán HMAC nếu chúng chia query theo những dấu phân cách khác nhau.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt dấu `?`, `&`, `=`, `;`, `#` và các percent escape như `%26`, `%3D` trong URL/query.
2. Mô tả cách parser xác định path, query, name và value mà không làm mất byte gốc trước khi canonicalize.
3. Giải thích các trường hợp **thiếu dấu bằng, giá trị rỗng, dấu phân cách thừa, tham số trùng, query rỗng** và ý nghĩa bảo mật của chúng.
4. Thiết kế một hợp đồng **StrictQueryV1** với chính sách dấu phân cách, thứ tự tham số, encoding và giới hạn tài nguyên rõ ràng.
5. Viết Java 17 để tạo canonical query xác định, đưa kết quả vào canonical HMAC request và kiểm tra test cases.
6. Nhận diện lỗi **HTTP parameter pollution**, double decoding và khác biệt parsing giữa client, proxy, verifier, framework/router.
7. Tách canonicalization khỏi chống replay, key rotation và authorization.

## 2. Cấu trúc URL/query và các dấu phân cách

Ví dụ:

~~~text
https://api.example.test/v1/orders?status=open&limit=10
\_________________________/\________/\__________________/
        authority              path         query
~~~

Dấu `?` đầu tiên **theo cấu trúc URI đã được parse** ngăn phần path với phần query. Trong phần query, nhiều API dùng `&` để tách các cặp tham số và `=` để tách tên với giá trị.

| Ký tự | Vai trò thường gặp | Điều cần quyết định trong contract |
| --- | --- | --- |
| `?` | Ngăn cách path với query | Query vắng mặt và query hiện diện nhưng rỗng có được coi giống nhau? |
| `&` | Phân cách các cặp trong cách biểu diễn key/value phổ biến | Có cho dấu `&` ở đầu/cuối, `&&`, hay cần escape khi nằm trong giá trị? |
| `=` | Phân cách tên và giá trị | Nếu có nhiều `=` thì tách ở dấu đầu hay từ chối? Giá trị rỗng có hợp lệ? |
| `;` | Một số framework/legacy parser cũng dùng làm dấu phân tách | Có cho `;` là dữ liệu hay là delimiter? Hai phía phải giống nhau |
| `+` | Thường biểu thị dấu cách trong `application/x-www-form-urlencoded` | Trong URI query khác, có thể được hiểu là dấu cộng literal; cần quy định |
| `%HH` | Percent-encoding cho byte đã mã hóa | Decode trước hay sau tách? Dấu phân cách đã encode được coi là dữ liệu hay cấu trúc? |
| `#` | Bắt đầu fragment của URI reference | Fragment thông thường không gửi đến HTTP server; raw `#` bất thường trong request-target phải bị xử lý rõ |
| `/` | Dùng trong path; cũng có thể xuất hiện trong query | Không được coi là dấu phân cách tham số chỉ vì có trong query |

**Lưu ý về tiêu chuẩn:** RFC 3986 định nghĩa thành phần query của URI, nhưng **không bắt mọi ứng dụng phải biểu diễn query dưới dạng các cặp `name=value` ngăn bằng `&`**. Cách diễn giải `name=value` và `&` là **quy ước của protocol/framework**, nên hợp đồng HMAC phải nêu chính xác cách dùng.

### 2.1. Tách path và query đúng ranh giới

~~~text
Request-target: /v1/orders?status=open&limit=10

Path:  /v1/orders
Query: status=open&limit=10
~~~

Trước khi làm gì khác, HTTP adapter cần phân biệt hai thành phần. Nếu verifier ký `/v1/orders` còn handler sử dụng `status=open&limit=10` để lọc quyền hoặc dữ liệu, thì **query cũng phải được ràng buộc vào chữ ký**.

Không dùng một hàm tùy tiện như `split("?")` trên chuỗi URL đã bị biến đổi nhiều lần, vì nó có thể mất thông tin query rỗng, xử lý sai trường hợp absolute-form, hoặc khác cách parser HTTP thật đọc request-target.

### 2.2. Dấu bằng tách ở đâu?

Xét:

~~~text
a=1
a=
a
a=1=2
=a
~~~

Các quy ước có thể khác nhau:

- `a=1`: thường là tên `a`, giá trị `1`.
- `a=`: giá trị là chuỗi rỗng.
- `a`: một số framework hiểu giá trị rỗng hoặc null; framework khác coi là flag.
- `a=1=2`: nhiều parser tách ở **dấu `=` đầu**, giá trị còn lại là `1=2`; parser nghiêm ngặt có thể từ chối.
- `=a`: có tên rỗng, đôi khi được chấp nhận; nhiều API nên từ chối.

Nếu client ký `a` như `a=` nhưng handler phân biệt hai dạng đó, verifier có thể xác minh một thông điệp không tương ứng với ý nghĩa nghiệp vụ. Hợp đồng ký phải quy định rõ **cặp không có dấu bằng** và **giá trị rỗng**.

### 2.3. Dấu & trống và tham số rỗng

~~~text
a=1&b=2
&a=1
a=1&
a=1&&b=2
&
~~~

Một số thư viện bỏ qua các phần rỗng, thư viện khác giữ chúng trong danh sách tham số. Khi canonicalizer tự bỏ phần rỗng còn router dùng phần rỗng theo nghĩa khác, hai request có thể được coi tương đương bởi HMAC nhưng khác nghĩa với ứng dụng.

**Chính sách đơn giản:** Nếu API không có yêu cầu hỗ trợ cặp rỗng, từ chối chúng thay vì im lặng xóa.

## 3. Dấu phân cách đã percent-encode

Percent-encoding biểu diễn byte qua `%HH`, ví dụ:

| Escape | Byte sau decode | Ký tự thường hiển thị |
| --- | --- | --- |
| `%26` | `0x26` | `&` |
| `%3D` | `0x3D` | `=` |
| `%3F` | `0x3F` | `?` |
| `%3B` | `0x3B` | `;` |
| `%2B` | `0x2B` | `+` |
| `%20` | `0x20` | Dấu cách |
| `%25` | `0x25` | `%` |

Một query:

~~~text
filter=red%26blue&mode=strict
~~~

nếu được parser theo `&` literal trước, sẽ cho hai cặp:

~~~text
filter = "red%26blue"  --decode 1 lần--> "red&blue"
mode   = "strict"
~~~

Nếu một tầng lại **decode toàn bộ query trước rồi mới split theo `&`**, nó có thể biến thành:

~~~text
filter=red&blue&mode=strict
~~~

khiến parser ở tầng sau hiểu thành ba phần. Đây là ví dụ điển hình của **decode–split order mismatch**.

### 3.1. Quy tắc quan trọng: tách và decode phải có thứ tự

Nếu protocol cho phép percent-encoding, cần quy định thứ tự xử lý rõ ràng, chẳng hạn:

1. Đọc **raw query** ở ranh giới tin cậy.
2. Tách cặp bằng **dấu `&` literal**, trước khi giải mã escapes.
3. Với mỗi cặp, xác định ranh giới `=` theo quy tắc của protocol.
4. Kiểm tra escape hợp lệ và decode **một lần** trong phạm vi từng name/value.
5. Chuẩn hóa UTF-8/Unicode/percent-encoding theo version.
6. So sánh, sắp xếp và serialize theo dạng canonical.
7. Bảo đảm handler sử dụng **cùng tập name/value đã xác minh** hoặc một diễn giải tương đương đã được chứng minh.

Vì cách xử lý percent escapes tương đối phức tạp, bài này xây dựng một **StrictQueryV1 không hỗ trợ percent-encoding**. Khi cần escape các ký tự phân cách trong giá trị, phải dùng contract V2 được thiết kế đầy đủ chứ không tự nới lỏng parser V1.

### 3.2. Dấu + và dấu cách

~~~text
q=a+b
q=a%20b
q=a%2Bb
~~~

Một form-style decoder có thể hiểu dấu `+` là dấu cách, nhưng một parser query URI khác có thể coi `+` là dấu cộng literal. Vì vậy, không dùng `URLDecoder` tùy tiện rồi cho rằng kết quả là canonical query cho mọi protocol.

Nếu API muốn hỗ trợ cả dấu cách và dấu cộng trong query value, contract phải quy định **form encoding hay URI encoding**, cách escape `+`, và normalize về biểu diễn nào. Nếu không thể thống nhất giữa client và gateway, có thể chuyển dữ liệu phức tạp sang JSON body và HMAC bảo vệ raw body hash.

### 3.3. Ký tự ? và # bên trong query

Theo ngữ pháp URI, ký tự `?` **có thể xuất hiện bên trong query**. Nó không nhất thiết bắt đầu một query mới. Ví dụ trong một hệ thống có thể có `next=/page?tab=1` như dữ liệu của query, nhưng một số cách parse thủ công sẽ xử lý sai.

Dấu `#` là dấu mở đầu fragment trong URI reference; fragment không được truyền trong request-target HTTP thông thường. Một request chứa `#` raw cần được xử lý theo protocol/wire parser, không mặc nhiên coi mọi phần sau `#` là query.

StrictQueryV1 trong bài **từ chối cả `?` và `#` bên trong raw query**, như một lựa chọn giới hạn để tránh nhập nhằng, không phải quy định chung rằng mọi URI query đều cấm `?`.

## 4. Tham số trùng và HTTP parameter pollution

Xét:

~~~http
GET /v1/reports?role=user&role=admin HTTP/1.1
~~~

Một số parser lấy **giá trị đầu tiên** (`role=user`), số khác lấy **giá trị cuối cùng** (`role=admin`) hoặc trả danh sách hai giá trị. Nếu verifier canonicalize bằng cách chỉ lấy một giá trị trong khi business handler lấy giá trị khác, request đã được ký theo một nghĩa nhưng được thực thi theo nghĩa khác.

Đây là một dạng **HTTP parameter pollution**.

### 4.1. Các chính sách có thể chọn

| Chính sách | `tag=a&tag=b` | Điều kiện an toàn |
| --- | --- | --- |
| Từ chối tên trùng | Bị từ chối | Dễ kiểm soát với API dùng tham số đơn trị |
| Cho phép multivalue có thứ tự | Giữ hai giá trị theo thứ tự | Ký thứ tự và router xử lý cùng danh sách |
| Cho phép multivalue không thứ tự | Canonicalize đa tập giá trị | Phải chứng minh thứ tự không ảnh hưởng ý nghĩa |
| First wins / last wins | Chọn một giá trị | Không nên dùng nếu các thành phần khác có thể chọn ngược |

Bài học chọn **từ chối duplicate keys** trong V1. Với API cần nhiều tag hoặc danh sách, có thể dùng repeated keys nhưng cần một **contract multivalue có version**, không tự chuyển từ `Map<String,String>` sang `Map<String,List<String>>` mà không đổi quy tắc ký.

### 4.2. Tham số ảnh hưởng quyền và xử lý nghiệp vụ

Giả sử handler đọc `tenantId` từ query:

~~~http
DELETE /v1/orders/42?tenantId=A&tenantId=B HTTP/1.1
~~~

Nếu verifier ký tenant A nhưng handler dùng tenant B, đó có thể là sai khác nghiêm trọng. Ngoài việc từ chối duplicates, **authorization không được lấy quyền truy cập từ query tự khai**, kể cả khi query đã HMAC ký bằng khóa client A. Quyền thực phải dựa trên principal và policy server-side.

## 5. Thứ tự tham số có phải dấu phân cách về mặt ngữ nghĩa không?

Hai query:

~~~text
a=1&b=2
b=2&a=1
~~~

có thể mang cùng ý nghĩa nếu API định nghĩa query là một **ánh xạ tên → giá trị đơn trị, không có thứ tự**. Tuy nhiên, nếu API phụ thuộc thứ tự hoặc có repeated keys, hai query có thể khác ý nghĩa.

Có hai lựa chọn thông dụng:

- **Preserve order:** ký đúng raw query hoặc danh sách cặp đã parse theo thứ tự, phù hợp khi thứ tự có ngữ nghĩa.
- **Canonical sort:** sắp xếp tên/value theo quy tắc byte xác định, phù hợp khi thứ tự không ảnh hưởng business logic.

Trong V1 của bài, query được hiểu là **unordered map với key duy nhất**. Vì thế client và verifier canonicalize bằng cách sắp xếp key theo thứ tự ASCII. Cách này **chỉ an toàn nếu router/handler cũng không phụ thuộc thứ tự raw query**.

Không dùng locale-sensitive sorting hoặc các so sánh bỏ qua chữ hoa/thường. `A` và `a` là **hai tên khác nhau** theo V1, và thứ tự sorting phải được xác định thống nhất.

## 6. Hợp đồng StrictQueryV1: dấu phân cách xác định

Để có một ví dụ đủ rõ để triển khai Java và test, ta định nghĩa một API mà query chứa **các tham số đơn trị không thứ tự**, với tên/giá trị chỉ dùng ký tự ASCII unreserved.

### 6.1. Đặc tả V1

1. HTTP adapter tách **path và raw query** đúng một lần theo request-target. Hàm canonicalizer **chỉ nhận raw query**, không nhận cả dấu `?`.
2. **Không có query** được biểu diễn bằng `null` ở API Java và canonical query là **chuỗi rỗng**.
3. **Có dấu `?` nhưng query rỗng** (raw query = `""`) bị **từ chối**. Như vậy `/orders` được phép, còn `/orders?` không được tự coi là tương đương.
4. Query có một hoặc nhiều cặp, phân cách bằng **dấu `&` literal**. Không có `&` ở đầu, cuối hoặc lặp `&&`.
5. Mỗi cặp bắt buộc có **chính xác một dấu `=` literal**.
6. Tên tham số **không rỗng**; giá trị **có thể rỗng**. `flag=` hợp lệ, nhưng `flag` không hợp lệ.
7. Tên và giá trị chỉ chứa `A-Z`, `a-z`, `0-9`, `-`, `.`, `_`, `~`. Không cho dấu cách, `+`, `;`, `?`, `#`, `%`, slash hoặc ký tự Unicode trong V1.
8. Tên tham số **phân biệt hoa/thường**. Không cho hai cặp có **cùng tên chính xác**.
9. Thứ tự cặp trong raw query không có ngữ nghĩa. Canonical query là các cặp đã **sắp xếp theo tên ASCII tăng dần** và nối bằng `&`.
10. Giới hạn ví dụ: tối đa **4.096 byte ASCII**, tối đa **50 cặp**. Kiểm tra trước khi thực hiện thao tác tốn chi phí.
11. Không trim, lowercase, percent-decode, bỏ cặp rỗng, collapse delimiter hay tự thêm `=`. Đầu vào ngoài contract phải bị từ chối.
12. Chữ ký HMAC ràng buộc **canonical query V1** vào canonical request có protocol version riêng.

**Đây là hợp đồng minh họa**, không phải một quy tắc được RFC 3986 áp đặt cho mọi HTTP API. Với dữ liệu như email, số điện thoại có `+`, URL lồng hoặc chuỗi Unicode, cần định nghĩa V2 hỗ trợ escaping hoặc đưa dữ liệu vào body theo contract ký.

### 6.2. Ví dụ canonicalization

| Raw query (không có dấu `?`) | Kết quả V1 | Giải thích |
| --- | --- | --- |
| `null` (vắng mặt) | `""` | Không có query |
| `a=1` | `a=1` | Một cặp hợp lệ |
| `b=2&a=1` | `a=1&b=2` | Sort theo tên |
| `a=1&b=2` | `a=1&b=2` | Đã theo thứ tự |
| `flag=` | `flag=` | Value rỗng được phép |
| `A=1&a=2` | `A=1&a=2` | Tên khác case, phân biệt |
| `a=1&empty=` | `a=1&empty=` | Hai cặp, value rỗng |
| `""` (query hiện diện nhưng trống) | **Từ chối** | `/path?` ngoài contract |
| `a` | Từ chối | Thiếu `=` |
| `=1` | Từ chối | Tên rỗng |
| `a=1=2` | Từ chối | Nhiều `=` |
| `a=1&` | Từ chối | Dấu `&` cuối |
| `&a=1` | Từ chối | Dấu `&` đầu |
| `a=1&&b=2` | Từ chối | Cặp rỗng ở giữa |
| `a=1&a=2` | Từ chối | Tên trùng |
| `a=1;b=2` | Từ chối | `;` không được cho phép |
| `q=a+b` | Từ chối | `+` không được cho phép |
| `q=a%20b` | Từ chối | Percent-encoding ngoài V1 |
| `q=a%26b` | Từ chối | Encoded delimiter ngoài V1 |
| `url=https://a` | Từ chối | Dấu `:` và slash ngoài V1 |
| `q=đơn` | Từ chối | Unicode ngoài V1 |
| `a=1?b=2` | Từ chối | `?` bên trong query ngoài V1 |
| `a=1#x` | Từ chối | `#` raw ngoài V1 |

### 6.3. Vì sao từ chối `a=1=2` thay vì lấy phần sau dấu = đầu tiên?

Một số parser coi `a=1=2` là tên `a`, giá trị `1=2`. Đó là một quy tắc có thể dùng nếu **được contract quy định và mọi tầng cùng tuân theo**.

StrictQueryV1 chọn **chính xác một dấu bằng** để dễ chứng minh parsing không nhập nhằng. Nếu giá trị cần chứa dấu `=`, có thể chuyển sang V2 có `%3D` và quy tắc parse/decode chặt chẽ.

### 6.4. Vì sao không đơn giản xóa dấu & thừa?

Nếu canonicalizer biến `a=1&&b=2` thành `a=1&b=2` nhưng handler giữ cặp rỗng hoặc xử lý dấu `&` khác, verifier đã chuẩn hóa mất một phần dữ liệu request. Chính sách “reject invalid input” giúp phát hiện sớm sự không tương thích của client.

### 6.5. V1 sắp xếp query nhưng không sửa HTTP request

V1 cho phép signer gửi raw query `b=2&a=1` và ký canonical query `a=1&b=2`. Điều này an toàn **chỉ trong giả định** application xử lý query như unordered map với unique keys. Nếu business handler dùng **thứ tự raw query** để quyết định nghiệp vụ, V1 không phù hợp. Khi đó hãy chọn hợp đồng preserve order hoặc thay đổi business API để order không có ý nghĩa.

## 7. Java 17: StrictQueryV1 canonicalizer

Ví dụ sau là một implementation đơn giản, có thể kiểm thử độc lập. Nó **không percent-decode** và không cần dùng `URLDecoder`. Vì V1 chỉ nhận ASCII unreserved, `String.compareTo` cho thứ tự từ điển tương ứng theo byte ASCII với các tên được phép.

~~~java
import java.util.SortedMap;
import java.util.StringJoiner;
import java.util.TreeMap;
import java.util.regex.Pattern;

public final class StrictQueryV1 {
    private static final Pattern NAME =
            Pattern.compile("[A-Za-z0-9._~-]+");
    private static final Pattern VALUE =
            Pattern.compile("[A-Za-z0-9._~-]*");

    private static final int MAX_QUERY_BYTES = 4096;
    private static final int MAX_PAIRS = 50;

    private StrictQueryV1() {}

    /**
     * rawQuery: null nếu URL không có dấu '?';
     *           "" nếu URL có '?' nhưng phần query rỗng;
     *           ngược lại là đúng raw query, không bao gồm '?' đầu.
     *
     * Hợp đồng: unordered unique-key map, mỗi cặp có đúng một '='.
     */
    public static String canonicalize(String rawQuery) {
        if (rawQuery == null) {
            return "";
        }

        if (rawQuery.isEmpty() ||
                rawQuery.length() > MAX_QUERY_BYTES) {
            throw new IllegalArgumentException("Invalid query");
        }

        // Pattern cho phép ASCII nên length == số UTF-8 bytes hợp lệ.
        String[] pairs = rawQuery.split("&", -1);
        if (pairs.length == 0 || pairs.length > MAX_PAIRS) {
            throw new IllegalArgumentException("Invalid query");
        }

        SortedMap<String, String> sorted = new TreeMap<>();
        for (String pair : pairs) {
            int equalsIndex = pair.indexOf('=');

            // Có đúng một '=', và name không rỗng.
            if (equalsIndex <= 0 ||
                    equalsIndex != pair.lastIndexOf('=')) {
                throw new IllegalArgumentException("Invalid query");
            }

            String name = pair.substring(0, equalsIndex);
            String value = pair.substring(equalsIndex + 1);

            if (!NAME.matcher(name).matches() ||
                    !VALUE.matcher(value).matches()) {
                throw new IllegalArgumentException("Invalid query");
            }

            // Value có thể là ""; duplicate key không được phép.
            if (sorted.putIfAbsent(name, value) != null) {
                throw new IllegalArgumentException("Duplicate query key");
            }
        }

        StringJoiner out = new StringJoiner("&");
        for (var entry : sorted.entrySet()) {
            out.add(entry.getKey() + "=" + entry.getValue());
        }
        return out.toString();
    }
}
~~~

Đặc tính của hàm:

- **Không có query** trả về chuỗi rỗng. **Query rỗng hiện diện** ném lỗi.
- `b=2&a=1` được chuẩn hóa thành `a=1&b=2`.
- Giá trị rỗng được giữ (`flag=`), không tự biến thành “không có tham số”.
- Tên tham số trùng bị từ chối trước khi tính chữ ký.
- Các ký tự `;`, `+`, `%`, `?`, `#`, `/`, Unicode, dấu cách đều bị từ chối do regex.
- Vì không decode, `%26` và `%3D` không được hiểu là delimiter hay dữ liệu hợp lệ trong V1.
- Độ dài và số lượng tham số có giới hạn; production còn cần giới hạn request-target tại HTTP server/gateway.

### 7.1. Ví dụ sử dụng

~~~java
assert StrictQueryV1.canonicalize(null).equals("");
assert StrictQueryV1.canonicalize("a=1").equals("a=1");
assert StrictQueryV1.canonicalize("b=2&a=1").equals("a=1&b=2");
assert StrictQueryV1.canonicalize("flag=").equals("flag=");
assert StrictQueryV1.canonicalize("A=1&a=2").equals("A=1&a=2");

// Các trường hợp phải ném IllegalArgumentException:
// "", "a", "=1", "a=1=2", "a=1&", "&a=1",
// "a=1&&b=2", "a=1&a=2", "a=1;b=2",
// "q=a+b", "q=a%20b", "q=đơn".
~~~

Để biến chúng thành unit test có ý nghĩa, viết `assertThrows` cho từng input, không chỉ ghi chú.

### 7.2. Khi nào dùng `Map`, khi nào không?

`TreeMap<String,String>` thích hợp ở đây **vì contract cấm duplicate keys và tuyên bố query không có thứ tự**. Không nên tái sử dụng đoạn code này cho:

~~~text
tag=java&tag=security
range=2026&range=2027
steps=one&steps=two
~~~

nếu API cần multivalue. Việc bỏ một giá trị hoặc tự gộp về cùng key có thể thay đổi nghĩa mà handler thực thi. V2 phải định nghĩa rõ danh sách cặp, cách sort theo name/value và quan hệ với thứ tự xử lý.

## 8. Đưa canonical query vào HMAC request signature

Một hợp đồng HMAC minh họa sử dụng:

- Algorithm: HMAC-SHA256.
- Canonical path: đã validate theo hợp đồng path riêng.
- Canonical query: `StrictQueryV1.canonicalize(rawQuery)`.
- Timestamp: Unix seconds, được ràng buộc vào HMAC.
- Nonce: giá trị ngẫu nhiên đủ mạnh, được ràng buộc vào HMAC.
- Key ID: chọn đúng shared secret còn hiệu lực do server quản lý.
- Body digest: SHA-256 của raw body bytes.
- Audience: service ID đáng tin như `orders-api`.
- Canonical text: UTF-8, các dòng nối bởi LF và **không có LF ở cuối**.

### 8.1. HTTP request ví dụ

~~~http
GET /v1/orders?status=open&limit=10 HTTP/1.1
Host: api.example.test
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <base64url-hmac-sha256>
~~~

Raw query: `status=open&limit=10`.

Canonical query V1: `limit=10&status=open`.

Nếu body là dãy byte rỗng, canonical request minh họa:

~~~text
HMAC-REQUEST-V1
GET
/v1/orders
limit=10&status=open
audience:orders-api
x-key-id:partner-a-k3
x-timestamp:1790000000
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<sha256-of-empty-body-hex>
~~~

Phần `<sha256-of-empty-body-hex>` là placeholder cho SHA-256 hex của byte rỗng. Protocol phải nêu **chính xác** các dòng được ký, quy tắc với header có/không có và cách xử lý raw body.

Chữ ký được tính:

~~~text
canonicalBytes = UTF8(canonicalRequest)
signatureBytes = HMAC-SHA256(K_mac, canonicalBytes)
X-Signature     = Base64URLWithoutPadding(signatureBytes)
~~~

Ở ví dụ này, thứ tự raw query có thể thay đổi từ `status=open&limit=10` sang `limit=10&status=open` mà canonical query **vẫn giống nhau**. Điều đó là có chủ đích vì contract định nghĩa query như **unordered unique-key map**. Ngược lại, sửa `limit=10` thành `limit=100` sẽ đổi canonical query và làm MAC cũ không còn khớp.

### 8.2. Query rỗng cần biểu diễn nhất quán

Request không có query:

~~~http
GET /v1/orders HTTP/1.1
~~~

Canonical query V1 là **chuỗi rỗng**. Trong canonical text, dòng dành cho query vẫn tồn tại dưới dạng **dòng trống**:

~~~text
HMAC-REQUEST-V1
GET
/v1/orders

audience:orders-api
...
~~~

Request có dấu `?` nhưng không có tham số (`GET /v1/orders?`) bị V1 **từ chối**, thay vì âm thầm tạo cùng canonical text. Điều này loại bỏ nhập nhằng giữa “query vắng mặt” và “query tồn tại nhưng rỗng”.

### 8.3. Không nhầm dấu phân cách của canonical request với delimiter query

Trong canonical text, mỗi phần lớn có thể được phân tách bằng **LF**, còn bên trong query các cặp được phân tách bằng **`&`** và key/value bằng **`=`**.

Không được nhầm hai lớp phân cách này. Trước khi nối canonical text, mọi field như method, path, key ID, timestamp, nonce và canonical query phải được validate để không chứa CR/LF hoặc các byte có thể phá format. Một yêu cầu an toàn hơn có thể sử dụng length-prefixed fields, nhưng ví dụ này dùng hợp đồng dòng LF cố định và input đã giới hạn.

## 9. Java 17: ký/xác minh HMAC với canonical query

Đoạn mã sau minh họa việc ghép canonical query V1 vào canonical request và tính HMAC với JCA. Nó giả định method/path/key ID/nonce đã được validate ở các tầng tương ứng.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SignedQueryRequest {
    private SignedQueryRequest() {}

    public static byte[] canonicalBytes(
            String method,
            String canonicalPath,
            String rawQuery,
            String keyId,
            long timestampSeconds,
            String nonce,
            byte[] rawBody) throws GeneralSecurityException {

        String canonicalQuery = StrictQueryV1.canonicalize(rawQuery);
        byte[] bodyHash = MessageDigest.getInstance("SHA-256")
                .digest(rawBody);
        String bodyHex = HexFormat.of().formatHex(bodyHash);

        // Mọi tham số ngoài query phải được validate riêng:
        // cấm CR/LF, path/query phải ở đúng ranh giới tin cậy.
        String canonical = String.join("\n",
                "HMAC-REQUEST-V1",
                method,
                canonicalPath,
                canonicalQuery,
                "audience:orders-api",
                "x-key-id:" + keyId,
                "x-timestamp:" + timestampSeconds,
                "x-nonce:" + nonce,
                "body-sha256:" + bodyHex);

        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static String sign(
            byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac.doFinal(canonicalBytes));
    }

    public static boolean verify(
            byte[] secret, byte[] canonicalBytes, String signature)
            throws GeneralSecurityException {

        if (signature == null
                || !signature.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        if (supplied.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(supplied).equals(signature)) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] expected = mac.doFinal(canonicalBytes);
        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

**Giới hạn của ví dụ:** Đây là helper mật mã và canonical query, **chưa phải HTTP authentication filter hoàn chỉnh**. Không nhận secret từ request, không tin key ID trước khi xác minh, không bỏ qua timestamp/nonce hoặc phân quyền.

Ngoài ra:

- `canonicalPath` phải được chuẩn hóa/validate theo hợp đồng path riêng.
- `method`, `keyId`, `nonce`, timestamp và các signed header khác phải được kiểm tra format và không chứa ký tự điều khiển.
- `rawBody` phải là đúng byte body theo ranh giới ký; tránh parse rồi serialize JSON lại.
- Signature Base64URL không padding của HMAC-SHA256 đầy đủ có 32 byte, biểu diễn thành **43 ký tự**.
- Production cần giới hạn body size, request timeouts, secret management, lỗi xác thực chung và kiểm soát log.

### 9.1. Lấy raw query từ HTTP adapter

Với Servlet API:

~~~java
String requestUri = request.getRequestURI();
String rawQuery = request.getQueryString();

// requestUri được xử lý theo hợp đồng canonical path riêng.
// rawQuery == null nghĩa là URL không có query.
// rawQuery.equals("") nghĩa là query hiện diện nhưng rỗng,
// và StrictQueryV1 sẽ từ chối.
String canonicalQuery = StrictQueryV1.canonicalize(rawQuery);
~~~

`getQueryString()` nói chung giữ query dưới dạng chưa decode theo Servlet API, nhưng proxy/container có thể đã rewrite request. Cần kiểm thử với gateway/framework thật, không mặc định giá trị đã đọc là nguyên vẹn từ client Internet.

Không dùng trực tiếp `request.getParameterMap()` để xây canonical query nếu chưa chứng minh nó giữ đủ thông tin cần thiết: nó có thể đã decode, gộp duplicate keys, xử lý `+` hoặc `;` theo cấu hình khác. StrictQueryV1 nên parse raw query trước, rồi truyền **tập tham số đã được chấp nhận** cho tầng nghiệp vụ hoặc bảo đảm handler parser tương thích.

## 10. Những lựa chọn ngoài StrictQueryV1

StrictQueryV1 rất dễ kiểm tra nhưng quá hạn chế với API cần email, số điện thoại, URL lồng trong query hay Unicode. Khi đó cần protocol v2 và quy tắc dấu phân cách/escape rõ ràng.

### 10.1. Hỗ trợ dấu phân cách trong value

Ví dụ muốn truyền literal value `red&blue`, request có thể dùng:

~~~text
color=red%26blue
~~~

V2 cần quy định:

- Dấu `&` literal dùng để tách cặp.
- `%26` khi decode trong **value** là dữ liệu literal `&`, không tạo cặp mới.
- `%3D` khi decode trong value là dấu bằng literal.
- Canonicalizer dùng biểu diễn percent-encode chuẩn và router không decode thêm lần nữa.
- Tên/giá trị sau decode phải có UTF-8 hợp lệ, giới hạn độ dài và không phá cấu trúc của signed fields.

**Không decode toàn bộ query trước khi tách `&`**.

### 10.2. Chấp nhận semicolon hay không?

Một số hệ thống cũ hoặc framework có thể chấp nhận `;` như delimiter. Nếu một tầng hiểu `a=1;b=2` là hai cặp còn tầng khác hiểu là một cặp `a → 1;b=2`, ta có parser differential.

Để hỗ trợ semicolon phải định nghĩa tường minh rằng nó có/không là delimiter, cách escape `%3B` và thứ tự canonicalize; đồng thời **không được để gateway và backend có quy tắc khác nhau**. Với thiết kế mới, thường đơn giản hơn khi chỉ cho dấu phân cách `&` theo contract.

### 10.3. Cặp trùng và tham số có thứ tự

API `tag=java&tag=security` có thể cần danh sách nhiều giá trị. V2 cần lựa chọn:

- Giữ nguyên thứ tự xuất hiện của các cặp hay sort theo name/value?
- `tag=java&tag=security` có tương đương `tag=security&tag=java` không?
- Tên trùng có phải được hiểu là một danh sách, hay có loại tham số chỉ được xuất hiện một lần?
- Router/framework có thực thi cùng mô hình không?

HMAC không tự quyết định những ngữ nghĩa này. Thiết kế signed query cần xuất phát từ **kiểu dữ liệu query mà handler thật sử dụng**.

### 10.4. Các giá trị có dấu + hoặc dấu cách

Nếu dùng `application/x-www-form-urlencoded`, `+` thường biểu diễn space; nếu dùng URI query tổng quát, dấu cộng có thể là ký tự literal. V2 phải công bố một mô hình rõ và xác nhận các thư viện JS/Java/Python có cùng kết quả trên test vectors:

~~~text
q=a+b
q=a%20b
q=a%2Bb
~~~

Không tự coi ba dạng này bằng nhau. Chúng có thể biểu diễn các giá trị khác nhau tùy parser.

### 10.5. Tham số chứa URL hoặc query lồng

~~~text
next=https%3A%2F%2Fexample.test%2Fpay%3Fa%3D1%26b%3D2
~~~

Nếu cần URL lồng, V2 phải encode nó như **một value**, không để dấu `?` hay `&` bên trong tạo thêm tham số ngoài. Canonicalizer và redirect handler cũng cần kiểm tra an toàn open redirect/SSRF riêng; HMAC đúng không chứng minh URL đích là an toàn hoặc được phép.

## 11. Proxy/gateway và khác biệt query parser

Luồng điển hình:

~~~mermaid
flowchart LR
    C[Client] --> G[WAF / API Gateway]
    G --> V[HMAC verifier]
    V --> R[Router / Framework query parser]
    R --> H[Business handler]
~~~

Gateway có thể:

- Sort hoặc reorder query parameters.
- Decode percent escapes hoặc chuyển `+` thành space.
- Gộp duplicate names theo “first wins”/“last wins”.
- Loại những cặp rỗng hoặc dấu `&` ở cuối.
- Parse và serialize lại URI, làm đổi escaping hoặc thứ tự.
- Thay path prefix hoặc authority; ảnh hưởng canonical request tổng thể.
- Retry request qua instance khác với replay store chưa đồng bộ.

### 11.1. Hai điểm xác minh

**Verifier tại gateway:** Gateway nhìn request ở biên, parse và ký theo đúng contract trước khi rewrite. Backend chỉ nhận principal/structured request context từ gateway qua kênh tin cậy, đồng thời phải bảo đảm dữ liệu query **mà handler sử dụng** chính là dữ liệu được xác minh, hoặc tương đương theo contract.

**Verifier tại backend:** Gateway cần giữ nguyên những byte/trường thuộc hợp đồng ký, hoặc có mapping biến đổi được định nghĩa để client và backend tái tạo cùng canonical request. Không được tin header `X-Original-Query` tự khai từ Internet; nếu dùng metadata từ proxy, proxy phải xóa input của client và bảo vệ kênh nội bộ.

### 11.2. Ví dụ parser differential

~~~http
GET /v1/orders?tenant=A;tenant=B HTTP/1.1
X-Key-Id: partner-a-k3
X-Signature: <illustrative-tag>
~~~

- Verifier có thể coi toàn bộ `tenant=A;tenant=B` là một cặp.
- Một parser legacy có thể tách ở `;` thành hai cặp.
- Handler có thể chọn giá trị cuối `tenant=B`, khác với giá trị mà verifier tưởng đã ký.

**Với StrictQueryV1, request này phải bị từ chối từ bước query validation.** Với V2 hỗ trợ semicolon, cần kiểm tra tất cả các tầng phân tích giống nhau; chữ ký hợp lệ không sửa được một hợp đồng parsing mơ hồ.

### 11.3. Kiểm thử end-to-end thật

Một unit test `StrictQueryV1.canonicalize()` là chưa đủ. Cần gửi request qua:

~~~text
Client -> Load balancer/WAF -> Gateway -> Verifier -> Framework -> Handler
~~~

Ở môi trường thử nghiệm có thể ghi nhận raw query tại biên, canonical query đã ký, tập tham số mà framework cung cấp và thao tác/tài nguyên cuối cùng. Dùng test secret và tránh log full signed request production có thể replay.

## 12. Dấu phân cách không giải quyết replay, key rotation và quyền

### 12.1. Timestamp và nonce chống replay

Một canonical query hoàn hảo không ngăn kẻ khác **phát lại nguyên một signed request** trong cửa sổ thời gian. Contract cần HMAC bảo vệ `X-Timestamp` và `X-Nonce`.

Server:

1. Kiểm tra timestamp nằm trong khoảng cho phép.
2. Tra secret theo key ID và tính lại HMAC trên canonical request.
3. Chỉ **sau khi MAC hợp lệ**, ghi nonce với thao tác `putIfAbsent` nguyên tử trong shared store.
4. Từ chối nonce đã sử dụng; TTL phải bao phủ toàn bộ thời gian request còn được chấp nhận.
5. Với thao tác nhạy cảm, cân nhắc fail closed khi store lỗi; idempotency xử lý lặp nghiệp vụ do retry mới.

### 12.2. Key rotation

~~~text
client: partner-a
keyId: partner-a-k2 -> secret v2, RETIRING
keyId: partner-a-k3 -> secret v3, ACTIVE
~~~

Verifier phải dùng đúng `keyId` đã được ký để tra key record, kiểm tra audience, trạng thái, thuật toán và secret tương ứng. Nếu thay đổi canonical query contract khi di trú, cần version hóa protocol và kiểm thử trên cả client/gateway/server. Không thử hàng loạt cách parse dấu phân cách và các secret cho đến khi tìm được tag khớp.

### 12.3. Authentication khác authorization

Một client có HMAC hợp lệ hoàn toàn có thể chủ động ký request:

~~~http
DELETE /v1/orders/42?tenant=B HTTP/1.1
X-Key-Id: tenant-A-client-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <valid-tag>
~~~

Canonical query `tenant=B` có thể đúng V1, timestamp/nonce có thể mới và HMAC có thể hợp lệ với secret của tenant A. **Không có nghĩa client A được phép xóa order của tenant B.** Sau xác thực, authorization phải đối chiếu principal, action, resource và tenant với chính sách server-side.

Không lấy tenant có quyền từ query do caller tự khai. Chữ ký chỉ bảo vệ rằng caller đã ký **yêu cầu đó**.

## 13. Ma trận kiểm thử dấu phân cách query

| Test | Raw query / tình huống | Kỳ vọng với StrictQueryV1 |
| --- | --- | --- |
| Query vắng mặt | `null` | Canonical query rỗng |
| Query hiện diện nhưng rỗng | `""` | Từ chối |
| Một cặp | `a=1` | Giữ `a=1` |
| Hai cặp đúng thứ tự | `a=1&b=2` | Giữ nguyên |
| Hai cặp đảo thứ tự | `b=2&a=1` | Canonical thành `a=1&b=2` |
| Giá trị rỗng | `flag=` | Chấp nhận |
| Chỉ tên | `flag` | Từ chối |
| Tên rỗng | `=1` | Từ chối |
| Hai dấu bằng | `a=1=2` | Từ chối |
| Dấu & đầu | `&a=1` | Từ chối |
| Dấu & cuối | `a=1&` | Từ chối |
| Hai dấu & liên tiếp | `a=1&&b=2` | Từ chối |
| Chỉ có & | `&` | Từ chối |
| Tên trùng | `a=1&a=2` | Từ chối |
| Tên khác case | `A=1&a=2` | Chấp nhận, phân biệt |
| Semicolon | `a=1;b=2` | Từ chối |
| Dấu cộng | `q=a+b` | Từ chối |
| Encoded ampersand | `q=a%26b` | Từ chối |
| Encoded equal | `q=a%3Db` | Từ chối |
| Encoded space | `q=a%20b` | Từ chối |
| Encoded percent | `q=a%2526b` | Từ chối |
| Dấu hỏi trong query | `a=1?b=2` | Từ chối theo V1 |
| Fragment marker raw | `a=1#frag` | Từ chối theo V1 |
| Dấu / trong value | `p=a/b` | Từ chối theo V1 |
| Unicode | `q=đơn` | Từ chối theo V1 |
| Dài quá giới hạn | Raw query hơn 4.096 byte | Từ chối sớm |
| Quá nhiều tham số | Hơn 50 cặp | Từ chối sớm |
| Sửa giá trị sau ký | `limit=10` → `limit=100` | HMAC cũ không khớp |
| Đổi thứ tự cặp hợp lệ | `a=1&b=2` → `b=2&a=1` | Canonical query giống nhau theo V1 |
| Đổi method/path sau ký | Giữ query/tag, thay method/path đã ký | HMAC không khớp |
| Body bị sửa | Thay byte body mà giữ tag | HMAC không khớp khi body digest được ký |
| Key bị thu hồi | Tag đúng bằng secret cũ | Từ chối do credential status |
| Timestamp cũ | Tag đúng nhưng quá hạn | Từ chối freshness |
| Nonce lặp | Gửi lại signed request | Từ chối replay |
| Replay đồng thời | Hai node nhận cùng nonce | Tối đa một request vượt replay gate |
| Gateway sort/rewrite | Proxy làm thay query byte hoặc semantics | Phải theo contract và bảo toàn ý nghĩa handler |
| Parameter pollution | `tenant=A&tenant=B` | Từ chối duplicate keys |
| Authenticated, sai tenant | Client A ký `tenant=B` | Authentication có thể đúng; authorization từ chối |

### 13.1. Differential test giữa các chuỗi

Nên so sánh các cặp:

~~~text
a=1&b=2       vs b=2&a=1
a=1           vs a=1&
a=1&b=2       vs a=1&&b=2
a=1           vs a
a=            vs a
q=a+b         vs q=a%20b
q=a%26b       vs q=a&b
role=user     vs role=user&role=admin
A=1&a=2       vs a=2&A=1
~~~

V1 phải có quyết định xác định cho từng cặp: chỉ những chuỗi **hợp lệ** theo V1 có cùng map key/value mới được canonicalize giống nhau. Mọi biến thể không thuộc contract phải bị từ chối, không được lén loại bỏ dữ liệu.

### 13.2. Test bằng raw HTTP, không chỉ object map

Khi kiểm thử, so sánh:

- Raw request-target tại gateway.
- Raw query tại verifier.
- Canonical query bytes mà client/verifier ký.
- Map/list query mà framework cung cấp cho handler.
- Route, resource ID, principal và authorization decision.

Các test quan trọng nhất là những trường hợp **verifier và handler có thể hiểu khác nhau**; chúng không thể được phát hiện chỉ bằng việc hai hàm HMAC cho cùng tag trên một chuỗi tùy ý.

## 14. Tình huống thực tế: webhook cập nhật đơn hàng

Một đối tác ký request để truy vấn và cập nhật trạng thái đơn:

~~~http
GET /v1/orders?status=pending&limit=10 HTTP/1.1
Host: api.example.test
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <hmac-tag>
~~~

Client dùng query gốc `status=pending&limit=10` nhưng HMAC ký canonical query `limit=10&status=pending`. Gateway giữ nguyên ngữ nghĩa query, verifier chọn secret của key ID, tái tạo chuỗi canonical và kiểm tra tag. Sau freshness và nonce, handler lọc đơn hàng thuộc **tenant của principal đã xác thực**.

**Tình huống A — đảo thứ tự:** Client gửi `limit=10&status=pending`. Với V1, canonical query giống nhau nên signature có thể khớp nếu mọi signed fields khác không đổi. Tuy vậy, request nonce đã dùng thì vẫn phải bị từ chối replay.

**Tình huống B — dấu & thừa:** Client gửi `status=pending&&limit=10`. V1 từ chối vì xuất hiện cặp rỗng. Không tự xóa `&` thừa trước khi ký.

**Tình huống C — semicolon:** Client gửi `status=pending;limit=10`. Nếu gateway xem `;` là delimiter nhưng backend không xem như vậy, có thể sai nghĩa. V1 từ chối để không phụ thuộc parser legacy.

**Tình huống D — giá trị có dấu &:** Client muốn truyền `q=red&blue` như **một giá trị**. V1 không hỗ trợ. Hãy dùng một contract V2 có `%26` trong value với quy tắc tách/decode chặt, hoặc truyền dữ liệu phức tạp qua body được ký.

**Tình huống E — tên trùng:** Client cố gửi `tenant=A&tenant=B`. V1 từ chối để ngăn parameter pollution. Ngay cả khi query chỉ có `tenant=B` và HMAC hợp lệ với secret A, authorization vẫn phải kiểm tra tenant thực tế.

## 15. Những lỗi triển khai thường gặp

### 15.1. Decode trước rồi mới split query

`%26` có thể biến thành dấu `&` literal rồi tạo tham số mới ở tầng sau. Nếu hỗ trợ percent encoding, tách dấu phân cách literal trước, decode mỗi name/value theo contract và ngăn double decoding.

### 15.2. Coi semicolon như & tại một tầng

Một gateway tách `;` nhưng backend không tách sẽ tạo parser differential. Đồng nhất contract hoặc từ chối semicolon.

### 15.3. Bỏ cặp rỗng và dấu & thừa

Việc âm thầm biến `a=1&&b=2` thành `a=1&b=2` có thể làm mất dữ liệu và dẫn tới ký một ý nghĩa khác request gốc. Chính sách StrictQueryV1 chọn từ chối.

### 15.4. Gộp tham số trùng bằng Map trước khi xác minh

Nếu handler lấy giá trị cuối trong khi canonicalizer giữ giá trị đầu, chữ ký sẽ bảo vệ giá trị không được thực thi. Chỉ dùng `Map<String,String>` sau khi đã bảo đảm **duplicate keys không tồn tại**.

### 15.5. Sử dụng URLDecoder bất kể query encoding

`URLDecoder` có semantics form encoding đối với dấu `+`. Không mặc nhiên áp dụng nó vào mọi URI query. Chọn chuẩn encoding và test giữa các client khác nhau.

### 15.6. Sort tất cả tham số khi thứ tự có ý nghĩa

Nếu handler xử lý `step=first&step=second` theo thứ tự, sorting làm mất nghĩa gốc. Cần preserve-order protocol hoặc khai báo structured body phù hợp.

### 15.7. Tin query đã ký là bằng chứng quyền

Client có secret thật vẫn có thể ký `tenant=B`. HMAC không chứng minh họ có quyền với B. Server phải kiểm tra authorization từ authenticated principal.

### 15.8. Bỏ query khỏi canonical request

Nếu query ảnh hưởng lọc, đối tượng hay action, thay query mà không cần thay HMAC sẽ làm cơ chế xác thực thiếu phạm vi. Ký canonical query cùng method, path, metadata và body digest cần thiết.

## 16. Bài tập tự thực hành

1. **Phân loại delimiter:** Với V1, cho biết kết quả của `a=1&b=2`, `b=2&a=1`, `a=`, `a`, `a=1=2`, `a=1&&b=2` và `a=1;b=2`.
2. **Viết unit test Java:** Dùng JUnit kiểm tra `StrictQueryV1.canonicalize()` trên các ca hợp lệ/không hợp lệ. Đặc biệt kiểm tra query vắng mặt (`null`) khác query hiện diện nhưng rỗng (`""`).
3. **Viết golden test:** Tạo request `GET /v1/orders?b=2&a=1`, xác định canonical query, body SHA-256 của byte rỗng, canonical bytes và HMAC Base64URL.
4. **Parameter pollution:** Tạo hai parser giả lập: “first wins” và “last wins” cho `tenant=A&tenant=B`. Chứng minh kết quả khác nhau rồi áp dụng policy từ chối duplicates ở ranh giới trước HMAC.
5. **Gateway test:** Gửi request thật qua reverse proxy với `%26`, `+`, `;`, `&&`, query order đảo và tên trùng. Đối chiếu raw query, canonical query và tập tham số trong handler.
6. **Replay và authorization:** Một client A gửi request mới, HMAC đúng, query `tenant=B`. Hãy giải thích vì sao nonce mới chưa đủ và bước authorization nào cần từ chối.

## 17. Checklist triển khai

- [ ] Contract phân biệt rõ path, query và các dấu `?`, `&`, `=`.
- [ ] Có quyết định tường minh cho query vắng mặt, query rỗng, flag thiếu `=` và value rỗng.
- [ ] Quy định dấu phân cách cặp literal, dấu `&` thừa, `&&`, dấu `=` lặp và tên trùng.
- [ ] Quy định có/không hỗ trợ semicolon delimiter, percent-encoding và dấu cộng form-encoding.
- [ ] Nếu percent-decode, tách các delimiter literal trước và decode name/value đúng một lần theo chuẩn đã chọn.
- [ ] Canonicalizer và framework handler cùng mô hình dữ liệu query, tránh first/last-wins mismatch.
- [ ] Quy định thứ tự (preserve hoặc sort) và ý nghĩa của repeated keys; không sort mù quáng.
- [ ] Giới hạn chiều dài query, số cặp, encoding và các ký tự điều khiển.
- [ ] Canonical query là thành phần được HMAC ký cùng method, path, audience và signed header/body quan trọng.
- [ ] Key ID gắn với secret đang hiệu lực, đúng audience/algorithm; rotation và revocation có quy trình kiểm soát.
- [ ] Timestamp/nonce được ký, server dùng shared nonce store nguyên tử và TTL đủ dài để chống replay.
- [ ] HTTPS/TLS bảo vệ kết nối; gateway không biến đổi query ngoài hợp đồng hoặc tạo parser differential.
- [ ] Authorization kiểm tra principal, action, resource, tenant độc lập với query do caller tự khai.
- [ ] Có positive, negative và end-to-end tests đi qua HTTP client, gateway, verifier và router thật.

## 18. Câu hỏi tự kiểm tra

1. **Dấu `?` dùng để làm gì?** Ngăn path với query trong URI, không phải delimiter giữa các cặp query.
2. **Dấu `&` có bắt buộc là separator theo mọi RFC URI không?** Không. Nó là quy ước key/value được hợp đồng HMAC trong bài chọn.
3. **`a=` và `a` có giống nhau trong V1 không?** Không. `a=` hợp lệ với giá trị rỗng; `a` bị từ chối vì thiếu `=`.
4. **Vì sao `a=1&&b=2` bị từ chối?** Vì có một cặp rỗng giữa hai dấu `&`.
5. **Vì sao không decode `%26` trước khi split?** Vì nó có thể biến dữ liệu của value thành dấu phân cách cấu trúc.
6. **`a=1&b=2` và `b=2&a=1` có cùng canonical query V1 không?** Có, vì V1 định nghĩa unordered unique-key map và sort theo tên ASCII.
7. **Vì sao `role=user&role=admin` bị từ chối?** Vì tên trùng có thể tạo first/last-wins mismatch và parameter pollution.
8. **Dấu `+` có luôn nghĩa là space trong HTTP query không?** Không; điều đó phụ thuộc quy tắc form encoding và parser.
9. **Query canonicalization có tự chống replay không?** Không. Cần timestamp, nonce và kho lưu nonce nguyên tử.
10. **Một query có HMAC đúng cho tenant B có cấp quyền cho client A không?** Không. Authorization phải kiểm tra principal và resource từ chính sách server.

**Kết luận:** Dấu phân cách query quyết định **ranh giới của dữ liệu được HMAC bảo vệ**. Một thiết kế an toàn cần công bố chính xác cách tách `?`, `&`, `=` và xử lý `;`, `+`, percent escapes, tham số trùng hoặc rỗng; sau đó bảo đảm signer, verifier, gateway và handler dùng cùng semantics. Chữ ký HMAC chỉ bảo vệ các byte đã được canonicalize; chống replay, quản lý khóa và phân quyền vẫn là những lớp kiểm soát độc lập.
