# Header validation

## 1. Mục tiêu: kiểm soát dữ liệu điều khiển request

HTTP header có thể ảnh hưởng tới cách hệ thống xác định đích đến, chọn parser, xác thực, phân tuyến, giới hạn lưu lượng và ghi audit. Vì vậy, header validation không chỉ là kiểm tra một chuỗi có rỗng hay không.

Trong đặc tả yêu cầu bảo mật, cần trả lời bốn câu hỏi:

1. Header nào được dùng cho quyết định nào?
2. Giá trị được nhận phải có cấu trúc, kích thước và số lần xuất hiện như thế nào?
3. Thành phần nào được quyền cung cấp giá trị đó?
4. Gateway, reverse proxy và ứng dụng có hiểu request theo cùng một cách không?

Bài học dùng hệ thống Orders API giả định: client đi qua edge gateway rồi tới ứng dụng Java. API có xác thực, phân quyền theo tenant và audit tập trung. Mọi giới hạn kích thước, tên header nội bộ và mã yêu cầu trong bài là lựa chọn minh họa của hệ thống này.

Không được coi một header là đáng tin chỉ vì tên bắt đầu bằng `X-`, có chữ `Internal` hoặc xuất hiện sau một reverse proxy.

## 2. Ba lớp validation cần tách rõ

| Lớp | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Giao thức | HTTP message có được parse hợp lệ không? | Tên field, framing, pseudo-header |
| Hợp đồng API | Header có đúng yêu cầu của route không? | Content-Type được hỗ trợ, mã tương quan đúng dạng |
| Nguồn tin cậy | Bên gửi có quyền khẳng định thông tin đó không? | Client IP do proxy tin cậy tạo, tenant đã đối chiếu |

Một header có thể đúng cú pháp nhưng sai hợp đồng. Một header đúng hợp đồng vẫn có thể đến từ nguồn không có thẩm quyền.

Ví dụ:

```http
X-Tenant-Id: tenant-example-a
```

Chuỗi trên có thể đúng định dạng mã tenant. Nó không chứng minh người gọi thuộc tenant đó. API vẫn phải liên kết giá trị với danh tính và quyền đã được xác minh.

Tương tự, `X-Forwarded-For` chứa một địa chỉ IP có cấu trúc hợp lệ không chứng minh địa chỉ đó là nguồn kết nối thật.

## 3. Nguyên tắc về tên, giá trị và số lần xuất hiện

### 3.1. Tên header và giá trị có quy tắc khác nhau

Theo [RFC 9110, mục 5.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.1), tên HTTP field không phân biệt chữ hoa chữ thường. Khi lập policy, `Authorization`, `authorization` và `AUTHORIZATION` phải được nhận diện là cùng một tên.

Điều đó không cho phép chuyển toàn bộ giá trị sang chữ thường. Token, mã ký hoặc dữ liệu tùy chỉnh có thể phân biệt hoa thường. Chuẩn hóa tên và diễn giải giá trị phải là hai thao tác riêng.

Trong triển khai, parser giao thức chịu trách nhiệm kiểm tra tên field theo phiên bản HTTP. Ứng dụng không nên nhận một khối byte tùy ý rồi tự dựng một HTTP parser bằng cách tách chuỗi theo dấu hai chấm.

### 3.2. Không dùng một quy tắc gộp cho mọi header

Một số field có ngữ nghĩa danh sách; một số có hợp đồng đơn trị. Không thể áp dụng “lấy giá trị đầu tiên”, “lấy giá trị cuối cùng” hoặc “nối mọi giá trị bằng dấu phẩy” cho tất cả field.

Trong Orders API, policy minh họa chọn:

| Header | Hợp đồng của API |
| --- | --- |
| Authorization | Tối đa một giá trị; route bảo vệ yêu cầu có credential phù hợp |
| Content-Type | Một giá trị cho request có body tại route nhập đơn |
| X-Tenant-Id | Một giá trị nếu route yêu cầu chọn tenant |
| X-Client-Request-Id | Tùy chọn, nhưng nếu có thì chỉ một giá trị |
| Accept | Parse theo ngữ nghĩa thương lượng nội dung |
| Cookie | Xử lý theo parser và quy tắc cookie, không gộp tùy ý |
| Forwarded | Chỉ diễn giải theo contract của chuỗi proxy tin cậy |

Các quy định đơn trị ở đây là hợp đồng sản phẩm. Chúng không phải kết luận rằng mọi HTTP field đều chỉ được xuất hiện một lần.

### 3.3. Phải còn bằng chứng về các giá trị trùng

Nếu thư viện đã biến hai dòng cùng tên thành một giá trị, code nghiệp vụ đọc một chuỗi sẽ không biết đầu vào ban đầu có trùng hay không.

Ví dụ trừu tượng:

```text
Gateway kiểm tra Authorization thứ nhất.
Ứng dụng lại sử dụng Authorization thứ hai.
=> Hai lớp có thể quyết định dựa trên credential khác nhau.
```

Do đó, requirement phải đặt kiểm soát duplicate tại nơi còn giữ được thông tin cần thiết. Nếu connector hoặc gateway đã gộp field, cần xác minh chính xác cách gộp và trường hợp bị từ chối, không chỉ kiểm tra một API getter tại controller.

Đây là một ví dụ về rủi ro các thành phần diễn giải HTTP request khác nhau, được phân loại tại [CWE-444](https://cwe.mitre.org/data/definitions/444.html).

## 4. Cú pháp bất thường, ký tự điều khiển và việc “sửa” đầu vào

Policy của Orders API yêu cầu parser HTTP ở edge từ chối input sai quy tắc giao thức trước khi chuyển tới ứng dụng. Đối với các header ứng dụng có hợp đồng ASCII chặt, giá trị chứa ký tự điều khiển hoặc xuống dòng không được chấp nhận.

Không dùng thao tác xóa CR, LF hoặc ký tự lạ để biến một giá trị sai thành giá trị mới rồi tiếp tục xử lý. Hai thành phần có thể sửa theo hai cách và tạo ra cách hiểu khác nhau.

Cũng không tự URL-decode mọi giá trị header. Chuỗi `%0d%0a` là các ký tự nhìn thấy được cho tới khi một thành phần áp dụng bước giải mã. Nó không tự trở thành CRLF trong mọi HTTP parser. Nếu ứng dụng có bước giải mã riêng, bước đó phải được đặc tả và kiểm tra theo ngữ cảnh sử dụng.

Quy tắc cần ghi rõ:

- Parser nào chịu trách nhiệm cho cú pháp giao thức.
- Những dạng tương thích cũ nào được nhận hoặc bị từ chối.
- Bước chuẩn hóa nào thực sự được phép.
- Thành phần phía sau có diễn giải lại dữ liệu không.
- Khi từ chối, request có bị chuyển tiếp hoặc tạo side effect không.

Với HTTP/1.1, sản phẩm ví dụ chọn từ chối dạng gấp dòng header cũ tại biên công khai. Đây là lựa chọn triển khai nghiêm ngặt cần được đối chiếu với khả năng cấu hình của server, không phải công việc để một filter Java sửa lại sau khi connector đã parse.

## 5. Framing phải được kiểm soát trước tầng nghiệp vụ

### 5.1. Content-Length và Transfer-Encoding

Các field liên quan framing ảnh hưởng tới ranh giới của message. Nếu proxy và backend xác định ranh giới khác nhau, một bộ kiểm tra header ở controller có thể đã quá muộn.

RFC 9112 mô tả thứ tự xác định độ dài message, xử lý Content-Length và Transfer-Encoding, cùng các trường hợp lỗi; xem [RFC 9112, mục 6.2–6.3](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3).

Orders API chọn policy cho luồng HTTP/1.1 công khai như sau:

- Từ chối request có cả Content-Length và Transfer-Encoding.
- Từ chối Content-Length lặp hoặc có biểu diễn nhiều giá trị, kể cả các giá trị bằng nhau.
- Từ chối giá trị độ dài sai cú pháp hoặc mâu thuẫn.
- Không chuyển request framing lỗi tới backend.
- Kết thúc kết nối theo xử lý lỗi framing của giao thức, tránh để dữ liệu thừa được dùng như request tiếp theo.

Chính sách từ chối mọi Content-Length lặp là lựa chọn chặt hơn một số trường hợp RFC cho phép chuẩn hóa. Đặc tả phải ghi rõ đây là policy tại edge, đồng thời kiểm tra rằng edge nhìn thấy đầu vào trước khi một lớp khác đã gộp nó.

### 5.2. Không áp dụng máy móc quy tắc HTTP/1.1 cho HTTP/2

HTTP/2 có pseudo-header, quy tắc field riêng và không dùng Transfer-Encoding để framing như HTTP/1.1. Tên field HTTP/2 phải viết thường và các field gắn với kết nối có những hạn chế riêng; xem [RFC 9113, mục 8.2](https://www.rfc-editor.org/rfc/rfc9113.html#section-8.2).

Một triển khai nhận HTTP/2 ở edge rồi gửi HTTP/1.1 tới backend cần có yêu cầu cho cả hai phía:

```text
Client -- HTTP/2 --> Edge -- HTTP/1.1 --> Java application
```

Việc edge nhận request hợp lệ theo một phiên bản không tự chứng minh request sau chuyển đổi vẫn có framing và authority nhất quán.

Không ép tất cả tình huống lỗi giao thức trả cùng một JSON response. Có lỗi được xử lý bằng stream error hoặc connection error trước khi tầng ứng dụng có thể tạo response. Điều cần bảo đảm là request không được thực thi và phản ứng tuân thủ giao thức.

## 6. Authority, Host và các URL do server tạo

Header liên quan authority có thể ảnh hưởng tới routing, link trong email, redirect hoặc cache key. Hệ thống cần biết host nào thực sự được phục vụ và nguồn nào được dùng để dựng URL tuyệt đối.

Trong Orders API:

- Gateway chỉ định tuyến các public authority đã được cấu hình.
- Ứng dụng không lấy Host bất kỳ của client làm base URL cho link nhạy cảm.
- Link xác nhận hoặc reset tài khoản dùng public base URL lấy từ cấu hình có thẩm quyền.
- X-Forwarded-Host của client không được thay thế cấu hình đó.
- Trường hợp authority giữa các thành phần không nhất quán phải có hành vi từ chối hoặc ánh xạ rõ ràng theo kiến trúc.

Kiểm tra authority cần parse host và port theo cơ chế đã chọn. Không dùng kiểm tra như `contains("example.test")` để chấp nhận miền. Chuỗi chứa tên miền hợp lệ ở một vị trí không chứng minh đó là host được phép.

Nếu sản phẩm hỗ trợ nhiều custom domain, allowlist không nhất thiết là một mảng hard-code. Nó có thể là mapping đã được xác minh và quản lý theo tenant; nhưng quyền thêm mapping cũng cần được kiểm soát.

Một tiêu chí quan trọng: thay header host ở request không được làm link nhạy cảm của server trỏ tới một đích do người gọi tùy ý chọn.

## 7. Forwarded header và ranh giới tin cậy của proxy

### 7.1. Cú pháp đúng chưa đủ để tin

RFC 7239 lưu ý rằng Forwarded có thể bị sửa bởi các node trên đường đi, kể cả client. Không thể dựa riêng vào sự hiện diện của field để tin nội dung; xem [RFC 7239, mục 8.1](https://www.rfc-editor.org/rfc/rfc7239.html#section-8.1).

Ví dụ một request công khai tự khai:

```http
X-Forwarded-For: 192.0.2.17
X-Forwarded-Proto: https
X-Authenticated-User: operator-example
```

Địa chỉ thuộc dải dùng cho tài liệu minh họa. Các dòng này không phải bằng chứng người gửi là proxy hoặc người quản trị.

### 7.2. Contract của hệ thống ví dụ

Orders API chọn một chuỗi tin cậy đơn giản:

1. Edge công khai nhận diện nguồn kết nối theo hạ tầng của nó.
2. Edge loại bỏ các header chuyển tiếp hoặc danh tính nội bộ do client tự gửi.
3. Edge tạo lại metadata đã được duyệt.
4. Chặng edge tới ứng dụng được bảo vệ và chỉ các peer được phép mới vào được.
5. Ứng dụng chỉ nhận metadata đó trên luồng đã xác thực nguồn proxy.

Nếu có nhiều proxy tin cậy, phải đặc tả cách mỗi hop thêm hoặc giữ dữ liệu và cách xác định điểm kết thúc của phần tin cậy. Không mặc định lấy địa chỉ đầu tiên hoặc cuối cùng từ danh sách mà không biết chuỗi triển khai.

Đặc biệt, không lấy client IP tự khai làm cách bỏ qua xác thực, mở endpoint quản trị hoặc xác định tenant. Ngay cả IP đã được suy ra đúng cũng không thay thế danh tính người dùng và quyền trên tài nguyên.

### 7.3. Ngăn đường đi vòng

Nếu ứng dụng có cổng trực tiếp cho phép client ngoài edge truy cập và vẫn tin X-Authenticated-User, policy “edge đã lọc header” chưa bảo vệ được hệ thống.

Bằng chứng nghiệm thu phải gồm cả topology thực tế, kiểm soát kết nối và hành vi khi metadata tin cậy thiếu hoặc đến từ peer không được phép.

## 8. Header quyết định cách xử lý body và credential

### 8.1. Content-Type và Content-Encoding

Route nhập đơn trong ví dụ chỉ nhận JSON theo hợp đồng đã công bố. Server phải parse media type bằng parser phù hợp và chọn đúng bộ xử lý body; không dùng so sánh chuỗi con như `contains("json")`.

Tên media type có quy tắc so sánh và tham số riêng được mô tả tại [RFC 9110, mục 8.3.1](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.3.1). Không chuyển toàn bộ header sang chữ thường rồi giả định mọi parameter value giữ nguyên ý nghĩa.

Hợp đồng sản phẩm phải ghi:

- Request có body nào bắt buộc Content-Type.
- Media type và tham số nào được hỗ trợ.
- Hành vi khi thiếu, sai, trùng hoặc không hỗ trợ.
- Body có được phép nén không.
- Giới hạn body trước và sau giải nén, nếu có giải nén.

Content-Type đúng không chứng minh body đúng schema. Content-Length nhỏ cũng không chứng minh dữ liệu sau giải nén nhỏ.

### 8.2. Authorization

Route có bảo vệ phải phân biệt:

- Header thiếu.
- Header trùng hoặc cấu trúc không hợp lệ.
- Cơ chế xác thực không được hỗ trợ.
- Credential không hợp lệ hoặc hết hạn.
- Credential hợp lệ nhưng không đủ quyền.

Bearer được truyền qua Authorization theo [RFC 6750, mục 2.1](https://www.rfc-editor.org/rfc/rfc6750.html#section-2.1). Kiểm tra header có tiền tố Bearer không thay thế việc xác minh token và đánh giá quyền.

Policy minh họa không gộp hai credential, không lấy một phần tùy ý từ giá trị chứa dấu phẩy và không ghi token vào lỗi. Parser xác thực phù hợp chịu trách nhiệm cho cú pháp của scheme; validator header tổng quát không tự sửa credential.

### 8.3. Origin và header do browser gửi

Origin có thể được dùng trong policy cho luồng browser, nhưng không phải chữ ký của người gửi. Client HTTP khác có thể tự đặt nhiều header mà browser thông thường kiểm soát.

Vì vậy, yêu cầu về Origin hoặc CORS phải được gắn với kịch bản browser cụ thể. API vẫn cần xác thực và phân quyền. Với cơ chế cookie, nhóm thiết kế còn phải đặc tả cách chống request giả mạo theo contract của luồng đó.

Nếu policy cần so sánh origin, dùng cấu trúc origin và mapping được duyệt; không chấp nhận bằng cách tìm một đoạn tên miền trong chuỗi. Trường hợp thiếu Origin hoặc giá trị null phải có quyết định riêng theo loại client được hỗ trợ.

## 9. Giới hạn kích thước, số lượng và thời gian đọc

Một yêu cầu “giới hạn header 16 KB” còn thiếu cách đo và nơi thực thi.

Orders API chọn ngân sách minh họa:

| Tham số | Chính sách ví dụ |
| --- | --- |
| Số field đầu request | Tối đa 64, tính cả field lặp |
| Tên field thường | Tối đa 128 octet |
| Một giá trị field | Tối đa 4.096 octet |
| Ngân sách field section đã giải nén | Tối đa 16.384 octet theo phép đo quy định |
| X-Client-Request-Id | Tối đa 64 ký tự ASCII theo grammar riêng |
| Thời gian nhận header | Có giới hạn tại connector/edge, cấu hình theo tải được duyệt |

Với HTTP/2, phép đo field section trong ví dụ dùng độ dài tên và giá trị sau giải nén cộng 32 octet cho mỗi field line, phù hợp cách mô tả tại [RFC 9113, mục 6.5.2](https://www.rfc-editor.org/rfc/rfc9113.html#section-6.5.2). Các pseudo-header phải được tính theo contract của connector, không bị bỏ ra khỏi ngân sách vô tình.

Với HTTP/1.1, cấu hình thường có cách đếm wire bytes khác. Nhóm triển khai cần ánh xạ các ngưỡng để không có lớp chấp nhận input vượt khả năng của lớp sau. Không giả định hai cấu hình cùng ghi “16 KB” có cùng phép đo.

Giới hạn kích thước nén không thay cho giới hạn sau giải nén. Giới hạn tổng cũng không thay cho giới hạn số field hoặc timeout đọc chậm. Đây là các chiều tài nguyên khác nhau.

Khi có thể trả response HTTP phù hợp, 431 là mã dành cho trường hợp request header quá lớn, được mô tả tại [RFC 6585, mục 5](https://www.rfc-editor.org/rfc/rfc6585.html#section-5). Không phản chiếu toàn bộ giá trị vượt ngưỡng vào response lỗi.

## 10. Từ mô hình đe dọa tới bộ requirement

| ID | Yêu cầu của Orders API | Rủi ro được kiểm soát | Owner chính |
| --- | --- | --- | --- |
| HV-01 | Parser từ chối message sai giao thức trước khi chuyển tới nghiệp vụ | Cách hiểu mâu thuẫn giữa các lớp | Platform team |
| HV-02 | Kiểm tra duplicate theo từng tên field và contract | Hai lớp dùng hai giá trị khác nhau | Gateway và API team |
| HV-03 | Request framing bất thường bị chặn tại edge | Desynchronization và xử lý request ngoài dự kiến | Gateway team |
| HV-04 | Authority dùng cho routing phải thuộc mapping có thẩm quyền | Routing hoặc URL tuyệt đối sai đích | Platform và tenant team |
| HV-05 | Chỉ tin metadata chuyển tiếp từ chuỗi proxy được bảo vệ | Giả IP, scheme hoặc danh tính nội bộ | Network và identity team |
| HV-06 | Content-Type và coding chỉ dẫn tới parser được hỗ trợ | Body được diễn giải ngoài hợp đồng | API team |
| HV-07 | Credential là đơn trị theo policy, được xác minh riêng | Nhầm credential và bypass xác thực | Identity team |
| HV-08 | Áp dụng giới hạn size, count và thời gian ở đúng lớp | Tiêu tốn bộ nhớ hoặc kết nối | Platform team |
| HV-09 | Header tương quan không trở thành nguồn danh tính | Giả audit, ghép nhầm sự kiện | Observability team |
| HV-10 | Lỗi không ghi credential hoặc phản chiếu input nguy hiểm | Rò bí mật và log injection | API và observability team |
| HV-11 | Sau chuyển đổi HTTP version, semantics vẫn nhất quán | Chênh lệch giữa HTTP/2 và HTTP/1.1 | Gateway team |
| HV-12 | Header bị từ chối không tạo side effect nghiệp vụ | Request lỗi vẫn được thực thi một phần | Service owner |

Các requirement cần đi kèm phạm vi route và hành vi ngoại lệ. Ví dụ một endpoint public không có Authorization không làm mất hiệu lực HV-07; nó phải được phân loại đúng là route không yêu cầu credential.

Không dùng allowlist tổng quát để xóa mọi header không nhận diện một cách tùy tiện. Field mở rộng hợp lệ có thể cần được bỏ qua hoặc chuyển tiếp theo protocol và contract. Riêng những field ảnh hưởng quyết định bảo mật phải có cách xử lý rõ, không để một thành phần sau tự diễn giải ngoài policy đã xét.

## 11. Ví dụ Java cho một header ứng dụng đơn trị

Đoạn code sau chỉ kiểm tra X-Client-Request-Id trên danh sách field mà connector đã parse hợp lệ. Nó không phải HTTP parser và không thay thế kiểm soát framing, authority hay giới hạn field section.

Hợp đồng của ví dụ:

- Header tùy chọn.
- Nếu xuất hiện, chỉ được có một giá trị sau khi nhận diện tên không phân biệt hoa thường.
- Giá trị gồm 1–64 ký tự ASCII, bắt đầu bằng chữ hoặc số; các vị trí sau có thể thêm dấu chấm, gạch dưới, gạch ngang.
- Không trim hoặc thay đổi giá trị để làm nó hợp lệ.
- Server luôn tạo request ID riêng; mã do client gửi chỉ là dữ liệu tương quan.

```java
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.regex.Pattern;

public final class RequestHeaderPolicy {
    private static final String CLIENT_ID_HEADER =
            "X-Client-Request-Id";

    private static final Pattern CLIENT_ID_FORMAT =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    public record Field(String name, String value) {
        public Field {
            Objects.requireNonNull(name, "name");
            Objects.requireNonNull(value, "value");
        }
    }

    public record Context(
            String serverRequestId,
            Optional<String> clientRequestId
    ) {
    }

    private RequestHeaderPolicy() {
    }

    public static Context validateAndCreateContext(
            List<Field> parsedFields
    ) {
        Objects.requireNonNull(parsedFields, "parsedFields");

        String clientId = null;
        int occurrences = 0;

        for (Field field : parsedFields) {
            Objects.requireNonNull(field, "field");

            if (!field.name().equalsIgnoreCase(CLIENT_ID_HEADER)) {
                continue;
            }

            occurrences++;
            if (occurrences > 1) {
                throw invalid("CLIENT_REQUEST_ID_DUPLICATE");
            }

            String value = field.value();
            if (value.length() > 64
                    || !CLIENT_ID_FORMAT.matcher(value).matches()) {
                throw invalid("CLIENT_REQUEST_ID_FORMAT");
            }
            clientId = value;
        }

        return new Context(
                UUID.randomUUID().toString(),
                Optional.ofNullable(clientId)
        );
    }

    private static IllegalArgumentException invalid(String code) {
        return new IllegalArgumentException(code);
    }
}
```

Ví dụ này dùng List để không tự đánh mất các lần xuất hiện cùng tên. Tuy nhiên, nếu connector đã gộp hai dòng trước khi tạo List, code không khôi phục được đầu vào gốc. Đó là lý do requirement về duplicate phải được xác minh ở toàn đường đi.

Đối với header này, dấu phẩy không thuộc grammar, nên giá trị đã bị gộp bằng dấu phẩy cũng bị từ chối. Điều đó không chứng minh cách làm tương tự đúng cho field danh sách như Accept.

Giá trị rỗng, có khoảng trắng hoặc chứa xuống dòng đều không đạt grammar. Exception chỉ mang mã cố định, không ghép nguyên giá trị lỗi vào thông báo.

Việc tạo server request ID riêng giúp tránh dùng mã do client kiểm soát như bằng chứng một sự kiện nội bộ đã xảy ra. Dù client ID đúng dạng, nó vẫn không phải định danh người dùng, tenant hoặc quyền truy cập.

## 12. Một đặc tả hoàn chỉnh cho duplicate header

Có thể ghi HV-02 cho route bảo vệ như sau:

```yaml
id: HV-02
title: Credential header không được mơ hồ
scope:
  route: Orders API protected routes
  entryPoints:
    - public gateway
    - application connector
field: Authorization
policy:
  nameComparison: case-insensitive
  maxOccurrences: 1
  duplicateBehavior: reject
  commaMergeBehavior: do-not-treat-as-multiple-credentials
requiredBehavior:
  - Không chọn giá trị đầu hoặc cuối để tiếp tục xác thực
  - Không chuyển request mơ hồ tới xử lý nghiệp vụ
  - Không ghi giá trị credential trong response hoặc telemetry
evidence:
  - Hai dòng cùng tên bị từ chối
  - Hai dòng khác kiểu chữ nhưng cùng tên bị từ chối
  - Kết quả nhất quán qua chuỗi gateway và ứng dụng
owner: Gateway team và identity team
```

Đây là nội dung requirement minh họa. Việc hiện thực cần dựa trên server, gateway và cơ chế xác thực đã chọn.

Từ requirement này có thể tạo các công việc riêng cho cấu hình edge, connector, tích hợp xác thực và kiểm chứng. Không đóng yêu cầu chỉ vì controller sử dụng một annotation đọc header.

## 13. Thiết kế tiêu chí kiểm chứng xuyên các lớp

Bảng dưới đây là kế hoạch kiểm chứng, không phải báo cáo một deployment đã chạy và đạt kiểm thử.

| Mã | Tình huống | Kết quả yêu cầu | Bằng chứng |
| --- | --- | --- | --- |
| V-01 | Đổi cách viết hoa tên header đơn trị trong HTTP/1.1 | Policy vẫn nhận diện cùng tên | Quyết định ở gateway và API |
| V-02 | Hai X-Client-Request-Id khác kiểu chữ | Từ chối duplicate | Mã lỗi; không có side effect |
| V-03 | Client ID dài 64 và 65 ký tự | 64 được nhận nếu đúng grammar; 65 bị chặn | Ca biên của validator |
| V-04 | Client ID chứa dấu phẩy hoặc khoảng trắng | Từ chối theo contract | Response và audit an toàn |
| V-05 | Authorization xuất hiện hai lần | Từ chối, không chọn một credential | Dấu vết của các lớp xác thực |
| V-06 | Content-Type đúng dạng nhưng không được route hỗ trợ | Không chọn parser ngoài hợp đồng | Response theo API contract |
| V-07 | Request HTTP/1.1 có cả CL và TE | Edge từ chối theo policy | Backend không nhận request nghiệp vụ |
| V-08 | Content-Length lặp bằng nhau hoặc khác nhau | Edge từ chối theo policy chặt của ví dụ | Quan sát trước bước gộp |
| V-09 | Client tự gửi Forwarded hoặc X-Authenticated-User | Không được tin như metadata nội bộ | Context thực tế tại ứng dụng |
| V-10 | Truy cập trực tiếp ứng dụng ngoài luồng proxy được phép | Không dùng được metadata giả để vào nghiệp vụ | Bằng chứng kiểm soát kết nối |
| V-11 | Thay authority thành đích ngoài mapping | Không định tuyến hoặc tạo link sai đích | Routing và URL do server tạo |
| V-12 | Nhiều field nhỏ vượt số lượng cho phép | Bị chặn theo ngân sách | Quyết định tại connector |
| V-13 | Field section nén nhỏ nhưng sau giải nén vượt ngân sách | Bị chặn theo giới hạn đã công bố | Kích thước theo phép đo thực tế |
| V-14 | Request hợp lệ qua HTTP/2 rồi HTTP/1.1 | Đích, credential và body được hiểu nhất quán | Metadata đã lọc ở hai phía |
| V-15 | Header lỗi chứa credential thử nghiệm hoặc ký tự đặc biệt | Không phản chiếu hoặc làm hỏng log | Response, log và telemetry |
| V-16 | Request bị từ chối trước controller | Không tạo đơn hoặc phát sự kiện thành công | Database và sự kiện trước/sau |

Các ca framing và chênh lệch parser phải thực hiện trong môi trường cô lập với dữ liệu thử nghiệm. Công cụ client cấp cao có thể tự sửa, gộp hoặc từ chối tạo input bất thường; cần biết chính xác dữ liệu nó đã gửi để không coi một ca chưa tới server là bằng chứng server đã chặn.

Trong HTTP/2, kiểm tra kiểu chữ trên wire phải tuân theo mục tiêu của ca kiểm chứng. Không suy rằng API nhận tên header không phân biệt hoa thường đồng nghĩa HTTP/2 cho phép gửi tên viết hoa trên wire.

Một kết quả 4xx đơn lẻ cũng chưa chứng minh toàn chuỗi an toàn. Cần biết lớp nào trả lỗi, lớp nào đã nhận request và có dữ liệu thừa hoặc tác động ngoài dự kiến tại backend không.

## 14. Lỗi, logging và vận hành

Một sự kiện audit an toàn có thể có dạng:

```json
{
  "event": "request_rejected",
  "request_id": "server-example-092",
  "route_id": "orders.create",
  "layer": "gateway",
  "reason": "duplicate_sensitive_header",
  "header_name": "authorization",
  "policy_version": "header-policy-example-3"
}
```

Không cần chứa Authorization để giải thích vì sao request bị từ chối. OWASP khuyến nghị loại các credential như access token khỏi log thông thường và kiểm soát dữ liệu ghi log; xem [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

Yêu cầu vận hành của hệ thống ví dụ gồm:

- Có thể đếm lỗi theo lớp, route và mã lý do.
- Tên header được ghi dưới dạng đã kiểm soát; giá trị bí mật không được ghi.
- Không ghi toàn bộ request headers khi bật debug.
- Bộ thu thập APM hoặc tracing áp dụng cùng chính sách dữ liệu.
- Việc thay đổi policy có phiên bản và owner.
- Chênh lệch mới giữa gateway và backend sau nâng cấp parser được xem là một thay đổi cần kiểm chứng lại.

Nếu không thể dựng response ứng dụng vì request đã bị connector chặn, hệ thống vẫn cần bằng chứng vận hành thích hợp tại lớp đó. Không nới parser chỉ để mọi lỗi đều đi qua controller và có cùng JSON body.

## 15. Những kết luận cần tránh

| Kết luận | Điểm còn thiếu trong requirement |
| --- | --- |
| “Header có đúng regex là đáng tin” | Chưa xác định nguồn có thẩm quyền |
| “Gateway đã xác thực nên backend đọc giá trị cuối cũng được” | Chưa chứng minh semantics của hai lớp giống nhau |
| “Chuyển mọi thứ sang chữ thường để chuẩn hóa” | Giá trị có thể phân biệt hoa thường |
| “Header trùng thì cứ nối bằng dấu phẩy” | Mỗi field có ngữ nghĩa riêng |
| “X-Forwarded-For đầu tiên là IP thật” | Chưa mô hình hóa proxy và phần chuỗi không tin cậy |
| “Đã bật HTTPS nên không cần kiểm tra Host” | Kênh bảo vệ không quyết định mapping authority của ứng dụng |
| “Chặn ở controller là đủ” | Framing và parser đã hoạt động trước controller |
| “Content-Type JSON thì body an toàn” | Chưa kiểm tra schema, kích thước và quyền trên dữ liệu |
| “Limit 16 KB ở mọi nơi là giống nhau” | Chưa quy định cách đếm, giải nén và số lượng field |
| “Có 4xx nghĩa là không có tác động” | Chưa kiểm chứng lớp phía sau và side effect |

Header validation tốt giữ cho các lớp cùng hiểu một request, kiểm soát đúng dữ liệu từ từng nguồn và có hành vi từ chối đo được. Yêu cầu hoàn chỉnh phải gắn cấu trúc header với quyết định bảo mật, nơi thực thi, nguồn tin cậy và bằng chứng xuyên suốt đường đi tới ứng dụng.
