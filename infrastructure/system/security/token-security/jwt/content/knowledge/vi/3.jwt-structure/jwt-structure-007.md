# Ảnh hưởng của khoảng trắng, thứ tự thuộc tính và cách tuần tự hóa

## 1. Vì sao cách tuần tự hóa JSON ảnh hưởng đến JWT?

JWT thường mang header và claims dưới dạng JSON. Trước khi đưa vào JWS hoặc JWE Compact, đối tượng JSON được chuyển thành văn bản JSON (*serialization*), sau đó thành byte UTF-8 và tiếp tục được xử lý theo định dạng JOSE.

Điểm cần hiểu là **chữ ký JWS gắn với chuỗi byte cụ thể**, không gắn với ý nghĩa trừu tượng của một JSON object. Vì vậy, hai văn bản JSON có thể biểu diễn cùng dữ liệu sau khi parse nhưng vẫn có byte khác nhau. Khi byte khác, Base64url segment và JWS Signing Input cũng khác; chữ ký được tạo cho cách biểu diễn này không xác minh được trên cách biểu diễn kia.

Ví dụ:

~~~json
{"sub":"customer-42","scope":"orders:read"}
~~~

và:

~~~json
{
  "sub": "customer-42",
  "scope": "orders:read"
}
~~~

Hai văn bản trên có thể được parse thành cùng một object. Nhưng chúng có khoảng trắng và xuống dòng khác nhau, nên byte UTF-8 khác nhau. Nếu dùng từng văn bản để tạo JWS, payload segment và chữ ký sẽ khác nhau.

Bài học này tập trung vào ba yếu tố thường làm thay đổi serialization:

- **Khoảng trắng và định dạng trình bày:** dấu cách, tab, xuống dòng và thụt lề.
- **Thứ tự thuộc tính:** thứ tự các cặp tên/giá trị trong JSON object.
- **Cách biểu diễn giá trị:** escape ký tự, Unicode, số và các tùy chọn của serializer.

Các yếu tố này cũng có thể ảnh hưởng đến JWE vì plaintext JSON được mã hóa từ byte cụ thể. Dù nội dung sau parse có cùng ý nghĩa, ciphertext vẫn có thể khác.

## 2. Từ object đến byte: serialization nằm ở đâu?

Một object trong bộ nhớ không tự có định dạng byte duy nhất. Thư viện hoặc thành phần phát hành cần serialize object thành JSON text. Các tùy chọn serializer quyết định cách biểu diễn văn bản đó.

~~~mermaid
flowchart TD
    A["JSON object trong ứng dụng"] --> B["JSON serializer"]
    B --> C["JSON text cụ thể"]
    C --> D["UTF-8 bytes"]
    D --> E["Base64url segment (JWS)"]
    E --> F["Signing Input"]
    F --> G["Signature/MAC"]
    D --> H["Plaintext bytes (JWE)"]
    H --> I["Mã hóa có xác thực"]
~~~

| Giai đoạn | Kết quả | Điều có thể thay đổi |
| --- | --- | --- |
| Object trong bộ nhớ | Cấu trúc thuộc tính và giá trị | Thứ tự lưu trữ nội bộ, kiểu số, kiểu chuỗi |
| Serialization | JSON text | Thứ tự thuộc tính, khoảng trắng, escape, cách viết số |
| UTF-8 encoding | Chuỗi byte | Byte phụ thuộc chính xác vào JSON text |
| Base64url | Segment văn bản | Thay đổi nếu byte đầu vào thay đổi |
| JWS Signing Input | ASCII của header segment, dấu chấm và payload segment | Thay đổi nếu một trong hai segment thay đổi |
| JWE encryption | Ciphertext và authentication tag | Phụ thuộc plaintext bytes, CEK, IV, AAD và thuật toán |

Do đó, khi phân tích một token, cần tách biệt:

- **Giá trị dữ liệu:** object mà ứng dụng muốn biểu diễn.
- **JSON text:** cách serializer viết object đó.
- **Byte gốc:** kết quả UTF-8 của JSON text.
- **Dữ liệu mật mã:** Signing Input của JWS hoặc plaintext/AAD của JWE.

Không thể suy ra byte gốc chỉ từ một object đã parse nếu không biết cách object đó đã được serialize.

## 3. Khoảng trắng: không đổi cấu trúc nhưng đổi byte

JSON cho phép khoảng trắng ở những vị trí cú pháp cho phép. Các ký tự thường gặp gồm dấu cách, tab, carriage return và line feed. Chúng giúp văn bản dễ đọc nhưng không nhất thiết là một phần của giá trị dữ liệu.

Ví dụ, ba cách viết sau có thể biểu diễn cùng object:

~~~json
{"sub":"u-42","active":true}
~~~

~~~json
{ "sub" : "u-42", "active" : true }
~~~

~~~json
{
  "sub": "u-42",
  "active": true
}
~~~

Nếu parse cả ba, ứng dụng có thể nhận cùng các cặp thuộc tính và giá trị. Tuy nhiên, các byte UTF-8 của chúng khác nhau:

- Cách thứ nhất không có khoảng trắng ngoài chuỗi.
- Cách thứ hai có dấu cách quanh dấu hai chấm và dấu phẩy.
- Cách thứ ba có xuống dòng và thụt lề.

Với JWS, thay đổi này làm payload JSON bytes, payload Base64url segment và Signing Input thay đổi. Signature cũ không còn phù hợp với Signing Input mới.

### Khoảng trắng bên trong chuỗi là dữ liệu

Không phải mọi khoảng trắng đều có thể bỏ. Khoảng trắng nằm **bên trong giá trị string** là một phần của giá trị:

~~~json
{"name":"An Nguyen"}
~~~

~~~json
{"name":"An  Nguyen"}
~~~

Hai giá trị name khác nhau vì chuỗi thứ hai có hai dấu cách giữa hai từ. Một serializer không được tùy tiện thu gọn khoảng trắng bên trong chuỗi.

### Khi nào có thể bỏ khoảng trắng?

Một serializer có thể tạo JSON dạng compact bằng cách loại bỏ khoảng trắng không cần thiết **bên ngoài string**, miễn là vẫn giữ đúng cú pháp và giá trị. Đây là lựa chọn định dạng khi phát hành token. Bên nhận không được tự xóa khoảng trắng trên token đã nhận rồi xác minh chữ ký cũ.

## 4. Thứ tự thuộc tính trong JSON object

Theo mô hình dữ liệu JSON, object là tập hợp các cặp tên/giá trị; thứ tự thuộc tính không mang ý nghĩa dữ liệu theo cách một mảng có thứ tự. Tuy nhiên, văn bản JSON vẫn phải viết các thuộc tính theo một thứ tự cụ thể.

Ví dụ:

~~~json
{"iss":"https://identity.example","sub":"u-42","aud":"orders-api"}
~~~

~~~json
{"aud":"orders-api","iss":"https://identity.example","sub":"u-42"}
~~~

Sau khi parse, hai object có thể mang cùng các thuộc tính và giá trị. Nhưng chuỗi JSON và byte UTF-8 khác nhau. Do đó, nếu tạo JWS từ hai cách viết, payload segment và signature sẽ khác nhau.

### Thứ tự mảng khác thứ tự object

Mảng JSON có thứ tự. Hai mảng sau **không tương đương về cấu trúc dữ liệu**:

~~~json
{"roles":["reader","auditor"]}
~~~

~~~json
{"roles":["auditor","reader"]}
~~~

Nếu ứng dụng gán ý nghĩa theo vị trí phần tử, đổi thứ tự mảng có thể làm thay đổi ý nghĩa nghiệp vụ, không chỉ thay đổi byte.

### Không dựa vào thứ tự thuộc tính ngầm định

Các ngôn ngữ, runtime và thư viện JSON có thể giữ hoặc sắp xếp thuộc tính theo quy tắc riêng. Một số serializer giữ thứ tự chèn; một số dùng thứ tự của kiểu map; một số có thể thay đổi thứ tự sau khi object được tạo hoặc chuyển đổi.

Nếu nhiều hệ thống cùng phát hành token và cần byte serialization ổn định, cần quy định rõ thứ tự thuộc tính hoặc dùng một chuẩn canonicalization mà tất cả các bên cùng hỗ trợ. Không nên giả định mọi serializer đều xuất ra cùng một thứ tự.

## 5. Escape ký tự và cách viết chuỗi

JSON có nhiều cách biểu diễn một số giá trị chuỗi. Các cách biểu diễn có thể khác byte nhưng sau khi parse lại cho cùng một giá trị.

Ví dụ dấu gạch chéo xuôi có thể viết trực tiếp hoặc escape:

~~~json
{"path":"/orders/42"}
~~~

~~~json
{"path":"\/orders\/42"}
~~~

Cả hai có thể parse thành cùng giá trị string /orders/42, nhưng JSON text khác nhau.

Ký tự điều khiển cũng có thể có nhiều cách viết escape:

~~~json
{"message":"line one\nline two"}
~~~

~~~json
{"message":"line one\u000aline two"}
~~~

Sau khi parse, hai chuỗi có thể chứa cùng ký tự line feed. Nhưng byte JSON đầu vào khác nhau.

Các trường hợp thường gặp:

| Giá trị cần biểu diễn | Cách viết JSON có thể gặp | Tác động |
| --- | --- | --- |
| Dấu gạch chéo / | / hoặc \/ | Cùng giá trị sau parse, byte khác |
| Xuống dòng | \n hoặc \u000a | Cùng ký tự điều khiển, byte khác |
| Dấu ngoặc kép trong string | \" | Cần escape để không kết thúc string |
| Dấu gạch chéo ngược | \\ | Cần escape chính dấu gạch chéo ngược |
| Ký tự Unicode | Ký tự UTF-8 trực tiếp hoặc \uXXXX | Có thể cùng giá trị Unicode nhưng byte khác |

Các serializer có thể cấu hình cách escape dấu /, ký tự ngoài ASCII, HTML-sensitive characters hoặc ký tự điều khiển. Nếu thay đổi cấu hình serializer, JSON bytes có thể thay đổi dù object đầu vào không đổi.

## 6. Unicode normalization và chuỗi nhìn giống nhau

Một vấn đề tinh tế hơn là hai chuỗi có thể nhìn gần như giống nhau nhưng chứa chuỗi code point Unicode khác nhau.

Ví dụ, ký tự é có thể được biểu diễn bằng:

- Ký tự dựng sẵn U+00E9.
- Chữ e U+0065 kết hợp dấu sắc U+0301.

Cả hai có thể hiển thị gần như giống nhau, nhưng chuỗi code point và byte UTF-8 khác nhau. JSON/JWT không tự động chuẩn hóa Unicode NFC hoặc NFD.

Điều này quan trọng với claim định danh như sub, username, email hoặc tên tổ chức. Nếu ứng dụng coi hai dạng Unicode là cùng một định danh nhưng một hệ thống chuẩn hóa còn hệ thống khác không chuẩn hóa, có thể phát sinh sai khác trong tra cứu, phân quyền hoặc so sánh dữ liệu.

Nguyên tắc xử lý:

1. Quy định rõ có chuẩn hóa Unicode cho từng trường nghiệp vụ hay không.
2. Nếu cần, chuẩn hóa dữ liệu ở thời điểm nhập hoặc trước khi phát hành token theo cùng một chính sách.
3. Không chuẩn hóa các segment của JWT đã nhận trước khi xác minh chữ ký.
4. Không dùng hình thức hiển thị giống nhau để kết luận hai chuỗi có byte hoặc giá trị code point giống nhau.

Chuẩn hóa Unicode là quyết định ở tầng dữ liệu ứng dụng; nó không phải bước tự động trong JWS.

## 7. Cách viết số và kiểu dữ liệu JSON

JSON có một kiểu Number, nhưng một giá trị số có thể có nhiều cách viết văn bản hợp lệ:

~~~json
{"amount":1}
~~~

~~~json
{"amount":1.0}
~~~

~~~json
{"amount":1e0}
~~~

Các biểu diễn này có thể được một ứng dụng hiểu là cùng giá trị số học, nhưng JSON text và byte khác nhau. Khi dùng trong JWS, chúng tạo ra payload segment và Signing Input khác nhau.

Cũng cần phân biệt số với chuỗi:

~~~json
{"exp":1893456300}
~~~

~~~json
{"exp":"1893456300"}
~~~

Hai payload này không tương đương về kiểu dữ liệu. Claim exp phải được biểu diễn theo kiểu NumericDate mà JWT quy định; chuỗi chứa chữ số không thay thế được Number.

Một số hệ thống còn có giới hạn về độ chính xác số. Các giá trị integer lớn có thể bị làm tròn khi đi qua runtime chỉ biểu diễn Number theo độ chính xác hữu hạn. Với mã định danh lớn, nên cân nhắc dùng String theo quy ước ứng dụng thay vì Number.

### NumericDate cần serialization nhất quán

Các claim exp, nbf và iat là NumericDate, biểu diễn số giây từ Unix epoch. Hệ thống phát hành nên thống nhất cách tạo giá trị số, tránh chuyển đổi qua lại giữa giây và mili giây hoặc giữa Number và String.

Không nên sửa giá trị exp chỉ để làm JSON dễ đọc hơn. Thay đổi giá trị thời gian thực sự sẽ làm thay đổi ý nghĩa và byte payload.

## 8. Tên thuộc tính trùng lặp và sự khác biệt giữa parser

JSON object nên có tên thuộc tính duy nhất. Ví dụ sau có hai thuộc tính cùng tên:

~~~json
{
  "sub": "customer-42",
  "sub": "administrator"
}
~~~

Các parser có thể xử lý tên trùng lặp khác nhau: giữ giá trị đầu tiên, giữ giá trị cuối cùng hoặc từ chối. Nếu một thành phần kiểm tra một giá trị nhưng thành phần khác sử dụng giá trị còn lại, hệ thống có thể hiểu cùng token theo hai cách.

Đây là vấn đề **không nhất quán khi diễn giải dữ liệu**, ngay cả khi chữ ký JWS hợp lệ. Chữ ký chỉ bảo vệ byte; nó không buộc mọi parser phải có cùng chính sách xử lý tên trùng lặp.

Đối với JWT, nên dùng parser có hành vi xác định và từ chối tên claim hoặc tham số JOSE trùng lặp theo chính sách phù hợp. RFC 8259 khuyến nghị tên trong object nên duy nhất; các đặc tả JOSE cũng có quy tắc riêng về tên tham số trùng lặp.

## 9. Tác động đến JWS: serialization tạo ra Signing Input

Quy trình JWS Compact có thể tóm tắt:

~~~text
headerJSON  -> UTF8 -> Base64url -> headerSegment
claimsJSON  -> UTF8 -> Base64url -> payloadSegment

signingInput = ASCII(headerSegment + "." + payloadSegment)

signature = SIGN(signingInput, key, algorithm)

token = headerSegment + "." + payloadSegment + "." + BASE64URL(signature)
~~~

Mọi thay đổi serialization của protected header cũng có thể làm header segment khác. Mọi thay đổi serialization của claims cũng có thể làm payload segment khác.

Ví dụ cùng một object claims nhưng hai serializer tạo hai payload segment:

~~~text
Serializer A:
{"sub":"u-42","scope":"read"}

Serializer B:
{ "sub": "u-42", "scope": "read" }
~~~

Do byte JSON khác nhau, payload segment khác nhau. Signing Input của hai token khác nhau, nên chữ ký được tạo cho Serializer A không thể dùng để xác minh token đã thay payload segment theo Serializer B.

### Bên nhận phải xác minh segment nguyên bản

Khi nhận JWS Compact:

- Tách ba segment và giữ nguyên chuỗi gốc.
- Tạo Signing Input từ nguyên văn headerSegment, dấu chấm ASCII và payloadSegment.
- Xác minh signature bằng thuật toán được phép và khóa tin cậy.
- Chỉ sau khi xác minh thành công mới parse claims để kiểm tra ý nghĩa và chính sách.

Không decode JSON rồi serialize lại để tạo Signing Input. Không tự sắp xếp thuộc tính, xóa khoảng trắng, chuẩn hóa Unicode hoặc đổi cách viết số trước khi verify.

## 10. Tác động đến JWE: plaintext bytes cũng phụ thuộc serialization

Với JWE Compact, JWT Claims Set được serialize thành JSON text rồi encode UTF-8 thành plaintext bytes. Các byte này được đưa vào thuật toán mã hóa nội dung cùng CEK, IV và AAD.

~~~text
claimsObject
    |
    v
JSON serialization
    |
    v
UTF-8 plaintext bytes
    |
    v
Authenticated encryption (CEK, IV, AAD)
    |
    +--> ciphertext
    +--> authentication tag
~~~

Nếu serializer thay đổi khoảng trắng, thứ tự thuộc tính hoặc escape, plaintext bytes thay đổi; ciphertext và authentication tag vì vậy cũng thay đổi.

Ngoài serialization, JWE dùng thuật toán mã hóa có xác thực thường có IV/nonce. Khi tạo token mới, IV mới có thể khiến ciphertext khác ngay cả khi plaintext và CEK giống nhau. Vì vậy, không nên so sánh hai JWE Compact bằng cách kỳ vọng chuỗi token phải giống hệt nhau.

Protected Header của JWE cũng được Base64url encode và tham gia AAD. Thay đổi cách serialize header làm header segment/AAD thay đổi; bên nhận phải xác thực theo chính xác segment gốc.

## 11. Canonicalization: khi nào cần một biểu diễn chuẩn?

**Canonicalization** là quá trình biến dữ liệu thành một dạng biểu diễn chuẩn theo quy tắc xác định. Mục tiêu là để cùng dữ liệu đầu vào tạo ra cùng chuỗi byte khi tất cả bên tham gia tuân thủ cùng quy tắc.

Một lựa chọn cho JSON là **JSON Canonicalization Scheme (JCS), RFC 8785**. JCS quy định cách serialize JSON theo hướng ổn định, bao gồm thứ tự thuộc tính và cách biểu diễn số, để các hệ thống có thể tạo cùng byte canonical từ cùng dữ liệu JSON phù hợp với các ràng buộc của chuẩn.

JCS có một số đặc điểm cần biết:

- Sắp xếp tên thuộc tính theo thứ tự UTF-16 code units theo quy tắc JCS.
- Dùng quy tắc serialization số tương thích với ECMAScript.
- Không tự chuẩn hóa Unicode thành NFC/NFD.
- Yêu cầu dữ liệu phù hợp với ràng buộc I-JSON; tên thuộc tính trùng lặp không được chấp nhận.
- Không phải mọi giá trị số tùy ý hoặc mọi kiểu dữ liệu ngoài JSON đều có thể được chuyển đổi mà không mất tính tương thích.

### JCS có bắt buộc với JWT/JWS không?

**Không.** JWS Compact thông thường ký Signing Input được tạo từ các segment đã Base64url nhận được. Đặc tả JWS không yêu cầu bên nhận canonicalize JSON trước khi xác minh.

Một giao thức ứng dụng có thể quy định dùng JCS để tạo nội dung trước khi ký, nhưng khi đó tất cả bên phát hành và bên nhận phải thống nhất chính xác cách áp dụng. Không được tự ý canonicalize một JWT đã nhận rồi dùng chữ ký cũ để xác minh.

Cần phân biệt hai trường hợp:

- **Tạo token mới:** có thể áp dụng một serializer hoặc canonicalization đã thỏa thuận trước khi tạo JWS.
- **Xác minh token đã nhận:** luôn dùng nguyên văn các segment Compact để tạo Signing Input theo JWS.

## 12. Cách giữ serialization ổn định khi phát hành token

Nếu một hệ thống cần tạo token có byte ổn định giữa các lần phát hành trong cùng điều kiện, nên kiểm soát quy trình serialization ngay từ đầu.

Một số thực hành hữu ích:

1. **Chọn một JSON serializer rõ ràng:** thống nhất thư viện và phiên bản hoặc quy tắc serialization giữa các thành phần phát hành.
2. **Cấu hình thứ tự thuộc tính:** nếu cần byte ổn định, dùng một quy tắc thứ tự xác định; không phụ thuộc vào thứ tự tình cờ của map hoặc object.
3. **Thống nhất khoảng trắng:** thường dùng compact JSON để giảm khác biệt định dạng.
4. **Thống nhất escaping:** quy định cách viết Unicode, dấu gạch chéo, ký tự điều khiển và các ký tự đặc biệt.
5. **Thống nhất kiểu số:** không luân phiên giữa String và Number; thống nhất cách tạo NumericDate và xử lý số lớn.
6. **Quy định Unicode:** xác định trường nào cần chuẩn hóa ở biên dữ liệu và dùng cùng quy tắc ở mọi bên.
7. **Từ chối tên thuộc tính trùng lặp:** tránh cách hiểu khác nhau giữa parser.
8. **Không thay đổi token sau khi ký:** lưu và truyền nguyên chuỗi Compact đã phát hành.

Nếu cần canonicalization theo chuẩn, hãy chọn chuẩn phù hợp và kiểm thử tính tương thích giữa các bên trước khi triển khai. Không nên tự phát minh một quy tắc canonical JSON riêng mà không có đặc tả rõ ràng.

## 13. Ví dụ thực tế: hai hệ thống serialize cùng claims

Một dịch vụ danh tính phát hành token cho API đơn hàng. Claims object:

~~~json
{
  "iss": "https://identity.example",
  "sub": "customer-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1893456300
}
~~~

Hệ thống A dùng serializer compact, giữ thứ tự thuộc tính theo lúc tạo object:

~~~json
{"iss":"https://identity.example","sub":"customer-42","aud":"orders-api","scope":"orders:read","exp":1893456300}
~~~

Hệ thống B sắp xếp thuộc tính theo alphabet và thêm khoảng trắng:

~~~json
{
  "aud": "orders-api",
  "exp": 1893456300,
  "iss": "https://identity.example",
  "scope": "orders:read",
  "sub": "customer-42"
}
~~~

Nếu cả hai payload sau parse có cùng các claim, chúng vẫn có byte khác nhau. JWS phát hành từ mỗi cách serialization có payload segment và Signing Input riêng. Không thể lấy signature của token A rồi thay payload segment bằng payload của token B mà mong chữ ký vẫn hợp lệ.

Nếu hai hệ thống muốn có cách biểu diễn canonical chung, chúng cần thống nhất một quy tắc serialization hoặc chuẩn như JCS trước khi ký. Nếu chỉ là API nhận token, API nên xác minh nguyên văn token nhận được, không serialize lại theo quy tắc nội bộ.

## 14. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ JSON có cùng ý nghĩa thì có cùng chữ ký | Bỏ qua khác biệt byte do serialization | Xác minh trên Signing Input gốc |
| Xóa khoảng trắng trước khi verify | Thay đổi payload segment | Không sửa token nhận được |
| Dựa vào thứ tự thuộc tính mặc định của runtime | Token phát hành giữa các thành phần có byte khác | Quy định serializer/thứ tự rõ ràng nếu cần |
| Bỏ khoảng trắng bên trong giá trị string | Thay đổi dữ liệu nghiệp vụ | Chỉ xử lý whitespace ngoài string theo cú pháp JSON |
| Chuẩn hóa Unicode ở một bên nhưng không ở bên kia | Khác biệt định danh và byte | Quy định normalization ở tầng dữ liệu |
| Đổi Number thành String hoặc ngược lại | Thay đổi kiểu claim và có thể làm sai validation | Giữ kiểu theo đặc tả claim |
| Không xử lý tên thuộc tính trùng lặp | Parser khác nhau có thể chọn giá trị khác nhau | Từ chối tên trùng lặp theo chính sách |
| Tự canonicalize trước khi xác minh | Chữ ký gốc không khớp dữ liệu mới | Verify trên segment gốc; canonicalize chỉ khi giao thức yêu cầu lúc phát hành |
| Mong JWE tạo cùng chuỗi ở mọi lần mã hóa | IV/nonce ngẫu nhiên và ciphertext có thể khác | So sánh plaintext sau giải mã có xác thực khi cần đối chiếu |

## 15. Tự kiểm tra kiến thức

1. Vì sao hai JSON khác khoảng trắng có thể tạo ra hai chữ ký JWS khác nhau?
2. Thứ tự thuộc tính object có thể khác mà vẫn parse ra cùng dữ liệu như thế nào?
3. Vì sao không được thay đổi thứ tự phần tử trong một array nếu thứ tự mang ý nghĩa?
4. Escape Unicode trực tiếp và dạng \uXXXX có thể giống nhau về giá trị nhưng khác byte ra sao?
5. Vì sao chuỗi Unicode nhìn giống nhau vẫn có thể có code point sequence khác?
6. `1`, `1.0` và `1e0` khác nhau thế nào ở lớp văn bản JSON?
7. Tại sao tên thuộc tính trùng lặp có thể gây rủi ro ngay cả khi chữ ký hợp lệ?
8. JCS giải quyết vấn đề serialization không ổn định ra sao?
9. Vì sao JCS không phải bước mặc định khi xác minh JWS Compact?
10. JWE có thể tạo ciphertext khác nhau dù plaintext JSON giống nhau vì lý do nào?

**Ghi nhớ:** Serialization quyết định JSON text; JSON text quyết định UTF-8 bytes; byte quyết định Base64url segment và dữ liệu mật mã tiếp theo. Khoảng trắng, thứ tự thuộc tính, escaping, Unicode và cách viết số đều có thể làm thay đổi byte dù dữ liệu sau parse có cùng ý nghĩa. Với JWS, bên nhận phải xác minh trên segment gốc; với JWE, plaintext bytes và AAD phải được xử lý đúng theo quy trình mã hóa có xác thực. Canonicalization chỉ được áp dụng khi giao thức đã quy định rõ.

### Tài liệu chuẩn để tra cứu

- **RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format:** cú pháp JSON, object, array, string, number và Unicode.
- **RFC 7515 — JSON Web Signature (JWS):** Signing Input và cách xác minh JWS Compact.
- **RFC 7516 — JSON Web Encryption (JWE):** plaintext, protected header và Additional Authenticated Data.
- **RFC 8785 — JSON Canonicalization Scheme (JCS):** quy tắc tạo biểu diễn JSON canonical.
- **RFC 8725 — JSON Web Token Best Current Practices:** xử lý JWT an toàn và tránh diễn giải không nhất quán.
