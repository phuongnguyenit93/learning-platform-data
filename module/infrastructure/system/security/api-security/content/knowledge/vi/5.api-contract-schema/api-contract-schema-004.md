# Unknown field, polymorphic type và mass assignment

API contract xác định client được phép gửi cấu trúc dữ liệu nào và service sẽ diễn giải cấu trúc đó ra sao. Ba vấn đề thường bị xem nhẹ trong quá trình deserialize JSON là trường không được khai báo (*unknown field*), kiểu dữ liệu đa hình (*polymorphic type*) và việc ánh xạ dữ liệu request vào thuộc tính nội bộ (*mass assignment*). Nếu hợp đồng không quy định rõ, client có thể gửi dữ liệu mà server không dự kiến, kích hoạt kiểu đối tượng ngoài phạm vi hoặc ghi đè thuộc tính mà người gọi không có quyền thay đổi.

Trong API Security, schema không chỉ giúp kiểm tra JSON có đúng cú pháp hay không. Schema còn là một phần của ranh giới tin cậy: nó giới hạn hình dạng dữ liệu được chấp nhận, làm rõ trường nào thuộc quyền điều khiển của client và giúp kiểm thử các đầu vào có thể gây thay đổi dữ liệu hoặc hành vi hệ thống.

## 1. Phân biệt ba vấn đề

| Vấn đề | Điều gì xảy ra? | Rủi ro điển hình |
|---|---|---|
| Unknown field | Request chứa thuộc tính không có trong schema hoặc DTO mà endpoint công bố | Client gửi nhầm trường, cố truyền thuộc tính nội bộ hoặc lợi dụng khác biệt giữa các parser |
| Polymorphic type | Một thuộc tính có thể đại diện cho nhiều kiểu con và JSON chọn kiểu cần deserialize | Attacker chọn kiểu ngoài dự kiến, kích hoạt quá trình khởi tạo đối tượng nguy hiểm hoặc vượt qua validation riêng của kiểu |
| Mass assignment | Server tự động chép nhiều thuộc tính từ request vào object/domain entity | Caller sửa `role`, `ownerId`, `tenantId`, `approved`, `balance` hoặc trạng thái mà họ không được phép điều khiển |

Ba vấn đề có liên quan nhưng không đồng nhất. Từ chối unknown field giúp giới hạn cấu trúc request, nhưng không tự động ngăn mass assignment nếu DTO vẫn chứa trường nhạy cảm. Polymorphic deserialization có thể chỉ sử dụng những trường đã biết nhưng vẫn nguy hiểm nếu client được quyền chọn một subtype không an toàn. Ngược lại, một endpoint chỉ nhận một DTO đơn giản vẫn có thể bị mass assignment nếu DTO được ánh xạ trực tiếp vào entity có nhiều thuộc tính hơn.

## 2. Xây dựng schema theo nguyên tắc allow-list

Với mỗi endpoint ghi dữ liệu, hãy xác định trước những trường client thực sự cần gửi. Schema nên mô tả rõ:

- Trường bắt buộc và trường tùy chọn.
- Kiểu dữ liệu, định dạng, độ dài, khoảng giá trị và số lượng phần tử.
- Tập giá trị hợp lệ của enum.
- Cấu trúc lồng nhau và giới hạn của từng phần tử.
- Trường nào được phép xuất hiện nhiều lần hoặc chứa thuộc tính mở rộng.
- Trường nào do server sinh ra và tuyệt đối không thuộc request contract.

Ví dụ, chức năng cập nhật hồ sơ cá nhân chỉ cần cho phép thay đổi tên hiển thị và số điện thoại. Client không cần gửi ID người dùng, tenant, role hoặc trạng thái tài khoản:

```json
{
  "displayName": "Nguyen An",
  "phoneNumber": "+84901234567"
}
```

Schema JSON có thể mô tả hợp đồng này như sau:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["displayName"],
  "properties": {
    "displayName": {
      "type": "string",
      "minLength": 1,
      "maxLength": 80
    },
    "phoneNumber": {
      "type": "string",
      "maxLength": 20
    }
  }
}
```

`additionalProperties: false` quy định object không được có thuộc tính ngoài danh sách `properties` đã khai báo. Nó giúp phát hiện request có trường không thuộc hợp đồng. Cần áp dụng quy tắc tương tự cho object lồng nhau nếu chúng cũng có cấu trúc cố định; khóa `additionalProperties` ở object ngoài không tự động đóng mọi object con.

Nếu một trường thực sự là map có khóa động, hãy khai báo rõ kiểu dữ liệu và giới hạn của value thay vì mở toàn bộ object. Ví dụ `labels` có thể cho phép các khóa tùy ý nhưng chỉ nhận chuỗi ngắn và giới hạn số lượng khóa theo validation của ứng dụng. Không nên dùng `additionalProperties: true` cho toàn bộ request chỉ để hỗ trợ một trường mở rộng.

## 3. Quyết định cách xử lý unknown field

Có hai chính sách thường gặp:

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| Reject | Từ chối request nếu có trường không được khai báo | Lệnh ghi, thao tác nhạy cảm, schema có cấu trúc rõ và client cần phát hiện lỗi hợp đồng |
| Ignore | Bỏ qua trường không được khai báo và tiếp tục xử lý các trường hợp lệ | Một số hợp đồng cần khả năng tương thích tiến hoặc có cơ chế extension được kiểm soát |

Với endpoint thay đổi trạng thái, tài khoản, quyền hoặc giao dịch, từ chối unknown field thường giúp phát hiện client gửi nhầm hoặc cố điều khiển thuộc tính ngoài hợp đồng. Lỗi có thể trả `400 Bad Request` với mã lỗi ổn định như `UNKNOWN_FIELD`, nhưng không cần phản chiếu toàn bộ giá trị do client gửi trong thông báo lỗi.

Chính sách ignore cũng có thể an toàn nếu server deserialize vào DTO allow-list và không ánh xạ request trực tiếp vào entity. Tuy nhiên, client có thể tưởng trường vừa gửi đã được áp dụng trong khi server âm thầm bỏ qua. Vì vậy hợp đồng phải nói rõ hành vi này, và kiểm thử phải xác nhận trường bị bỏ qua không tạo ra thay đổi ngoài dự kiến.

Không chọn chính sách chỉ dựa vào một cấu hình Jackson toàn cục. Một ứng dụng có thể nhận payload từ nhiều nguồn và có yêu cầu tương thích khác nhau. Nếu bật từ chối unknown field trên toàn ứng dụng, cần đánh giá ảnh hưởng tới webhook, message consumer và tích hợp hiện có. Có thể áp dụng validator hoặc cấu hình mapper theo boundary phù hợp, nhưng không tạo ra nhiều cách diễn giải JSON khó kiểm soát.

Ngoài unknown field, nên thống nhất cách xử lý các đầu vào nhập nhằng:

- **Trùng tên thuộc tính trong JSON:** một số parser lấy giá trị đầu tiên, một số lấy giá trị cuối. Nên bật chế độ phát hiện duplicate key ở parser nếu stack hỗ trợ và từ chối payload có khóa trùng.
- **Sai kiểu:** không tự ép chuỗi thành số hoặc số thành boolean ngoài hợp đồng. Từ chối kiểu không hợp lệ thay vì đoán ý định client.
- **Giá trị null:** phân biệt trường bị bỏ qua với trường có mặt nhưng mang `null`, nhất là trong thao tác cập nhật một phần.
- **Tên trường không nhất quán:** tránh hỗ trợ nhiều alias hoặc cách viết khác nhau nếu chúng có thể cùng ánh xạ vào một thuộc tính nhạy cảm.

Các thành phần ở gateway, validator, application và service downstream cần thống nhất cách diễn giải request. Nếu gateway kiểm tra một dạng nhưng service lại deserialize theo quy tắc khác, attacker có thể khai thác chênh lệch giữa các lớp.

## 4. Unknown field trong OpenAPI

OpenAPI giúp công bố request contract cho client, sinh tài liệu và hỗ trợ kiểm tra tương thích. Với OpenAPI 3.1, schema sử dụng nền tảng JSON Schema; có thể mô tả object đóng bằng `additionalProperties: false`:

```yaml
openapi: 3.1.0
info:
  title: Profile API
  version: 1.0.0
paths:
  /api/me/profile:
    patch:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UpdateProfileRequest'
      responses:
        '204':
          description: Profile updated
        '400':
          description: Request does not match the contract
components:
  schemas:
    UpdateProfileRequest:
      type: object
      additionalProperties: false
      required:
        - displayName
      properties:
        displayName:
          type: string
          minLength: 1
          maxLength: 80
        phoneNumber:
          type: string
          maxLength: 20
```

Schema là hợp đồng và công cụ kiểm tra; nó không tự đảm bảo runtime đã thực thi đúng quy tắc. Hãy xác minh framework validation, JSON deserializer và mapper đều có hành vi tương ứng. Với OpenAPI 3.0, một số khác biệt về dialect JSON Schema có thể ảnh hưởng cách công cụ xử lý; cần kiểm tra theo phiên bản OpenAPI và validator thực tế đang dùng.

## 5. Polymorphic type: vì sao trường chọn kiểu cần được kiểm soát?

Polymorphism hữu ích khi một endpoint nhận nhiều biến thể có cấu trúc khác nhau. Ví dụ lệnh thanh toán có thể là thanh toán bằng thẻ đã token hóa hoặc chuyển khoản. Một discriminator như `kind` cho biết JSON thuộc biến thể nào:

```json
{
  "kind": "card",
  "tokenizedCardId": "card_tok_123"
}
```

hoặc:

```json
{
  "kind": "bank_transfer",
  "bankAccountReference": "acct_ref_456"
}
```

Rủi ro xuất hiện khi server cho phép client cung cấp tên class, tên package hoặc type identifier tùy ý rồi dùng giá trị đó để khởi tạo class. Một số cơ chế deserialize đa hình có thể tạo ra object có hành vi hoặc side effect mà endpoint không dự kiến. Việc deserialize thành công không có nghĩa là kiểu đó phù hợp với nghiệp vụ hoặc người gọi được phép sử dụng nó.

Các nguyên tắc an toàn:

1. Dùng discriminator có giá trị nghiệp vụ cố định, ví dụ `card` hoặc `bank_transfer`.
2. Ánh xạ discriminator qua allow-list các subtype đã biết trong code và hợp đồng API.
3. Từ chối type identifier không được khai báo; không fallback sang class tùy ý.
4. Không bật cơ chế tự động cho phép deserialize class theo tên do request cung cấp, chẳng hạn default typing rộng hoặc type metadata chứa fully qualified class name.
5. Validate riêng các trường của từng subtype và kiểm tra quyền sử dụng subtype đó.
6. Giữ các quyết định nhạy cảm như giá, chủ tài khoản, trạng thái thanh toán và quyền thực hiện ở phía server.

Discriminator chỉ giúp chọn cấu trúc. Nó không phải bằng chứng về quyền hạn, danh tính hay độ tin cậy của dữ liệu.

## 6. Khai báo polymorphism an toàn trong OpenAPI

Với OpenAPI 3.1, có thể kết hợp `oneOf` với discriminator và schema đóng cho từng biến thể:

```yaml
components:
  schemas:
    PaymentRequest:
      oneOf:
        - $ref: '#/components/schemas/CardPaymentRequest'
        - $ref: '#/components/schemas/BankTransferPaymentRequest'
      discriminator:
        propertyName: kind
        mapping:
          card: '#/components/schemas/CardPaymentRequest'
          bank_transfer: '#/components/schemas/BankTransferPaymentRequest'

    CardPaymentRequest:
      type: object
      additionalProperties: false
      required:
        - kind
        - tokenizedCardId
      properties:
        kind:
          type: string
          const: card
        tokenizedCardId:
          type: string
          minLength: 1
          maxLength: 100

    BankTransferPaymentRequest:
      type: object
      additionalProperties: false
      required:
        - kind
        - bankAccountReference
      properties:
        kind:
          type: string
          const: bank_transfer
        bankAccountReference:
          type: string
          minLength: 1
          maxLength: 100
```

`oneOf` yêu cầu dữ liệu phù hợp chính xác một schema trong danh sách. `discriminator` giúp công cụ hiểu cách ánh xạ biến thể, nhưng không thay thế validation của `oneOf` và các schema con. Không khai báo subtype chỉ trong code mà quên cập nhật hợp đồng, hoặc công bố subtype trong OpenAPI nhưng runtime lại chấp nhận một tập kiểu khác.

Với mỗi biến thể, hãy giới hạn trường hợp lệ và trường bắt buộc riêng. Ví dụ biến thể `card` không nên nhận `bankAccountReference`; biến thể `bank_transfer` không nên nhận `tokenizedCardId`. Những trường nhạy cảm như `amount`, `customerId` hoặc `paymentStatus` nên được server lấy từ dữ liệu đáng tin cậy thay vì nhận từ payload nếu nghiệp vụ không yêu cầu client cung cấp.

## 7. Ví dụ Java: allow-list subtype với Jackson

Với Jackson, có thể khai báo các subtype được phép bằng tên logic cố định. Ví dụ dưới đây minh họa cấu trúc request; các annotation validation và quy tắc nghiệp vụ cần được bổ sung theo ứng dụng:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind")
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPaymentRequest.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferPaymentRequest.class,
                name = "bank_transfer")
})
public sealed interface PaymentRequest
        permits CardPaymentRequest, BankTransferPaymentRequest {
}

public record CardPaymentRequest(
        @NotBlank @Size(max = 100) String tokenizedCardId)
        implements PaymentRequest {
}

public record BankTransferPaymentRequest(
        @NotBlank @Size(max = 100) String bankAccountReference)
        implements PaymentRequest {
}
```

`JsonTypeInfo.Id.NAME` dùng tên subtype đã đăng ký như `card`, thay vì yêu cầu client gửi tên class Java. Giá trị `kind` không nằm trong record con ở ví dụ này vì Jackson dùng nó để chọn subtype. Nếu hợp đồng cần expose discriminator rõ ràng trong model hoặc cần validate nó theo cách khác, hãy thiết kế DTO phù hợp với phiên bản Jackson đang dùng.

Không bật `ObjectMapper` default typing rộng cho payload không tin cậy. Cấu hình allow-list ở trên vẫn cần được kiểm tra cùng cấu hình mapper thực tế, module đã đăng ký và các subtype có thể được nạp. Hãy có test chứng minh type không xác định bị từ chối và không có fallback tạo object ngoài danh sách.

Sau khi deserialize, tiếp tục validate theo subtype và authorization. Ví dụ, một merchant có thể được phép dùng chuyển khoản nhưng không được dùng một loại thanh toán khác; điều đó phải được kiểm tra ở service theo principal và chính sách tài khoản.

## 8. Mass assignment: lỗi khi request điều khiển thuộc tính nội bộ

Mass assignment xảy ra khi ứng dụng tự động gán một tập trường từ request vào object có nhiều thuộc tính hơn những gì client được phép thay đổi. Ví dụ entity người dùng có thể chứa:

```java
@Entity
class UserEntity {
    UUID id;
    UUID tenantId;
    String email;
    String displayName;
    String phoneNumber;
    String role;
    boolean enabled;
    boolean verified;
}
```

Nếu endpoint nhận trực tiếp entity hoặc chép toàn bộ thuộc tính JSON vào entity, caller có thể thử gửi:

```json
{
  "displayName": "An",
  "role": "ADMIN",
  "tenantId": "another-tenant-id",
  "enabled": true,
  "verified": true
}
```

Ngay cả khi giao diện chỉ hiển thị ô `displayName`, attacker vẫn có thể gửi các trường khác bằng HTTP client. Nếu mapper tự động copy các trường trùng tên, caller có thể thay đổi quyền, tenant hoặc trạng thái tài khoản.

Các thuộc tính có rủi ro cao thường gồm:

- Định danh và quan hệ sở hữu: `id`, `ownerId`, `customerId`, `tenantId`.
- Quyền và trạng thái tài khoản: `role`, `permissions`, `enabled`, `verified`, `isAdmin`.
- Dữ liệu tài chính hoặc giá trị được tính ở server: `balance`, `price`, `discount`, `refundAmount`.
- Trạng thái quy trình: `approved`, `paymentStatus`, `createdBy`, `reviewedAt`.
- Thuộc tính audit và concurrency: `createdAt`, `updatedBy`, `version`.

## 9. Ngăn mass assignment bằng request DTO và mapping tường minh

Tạo DTO riêng cho mỗi thao tác và chỉ đưa vào đó các trường client được phép điều khiển. Sau khi xác thực và phân quyền, service đọc entity theo phạm vi của caller rồi gán từng trường được phép:

```java
public record UpdateProfileRequest(
        @NotBlank @Size(max = 80) String displayName,
        @Size(max = 20) String phoneNumber) {
}

@RestController
@RequestMapping("/api/me/profile")
@RequiredArgsConstructor
class ProfileController {
    private final ProfileService profileService;

    @PatchMapping
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void updateProfile(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody UpdateProfileRequest request) {
        profileService.update(jwt.getSubject(), request);
    }
}

@Service
@RequiredArgsConstructor
class ProfileService {
    private final UserRepository userRepository;

    @Transactional
    void update(String subject, UpdateProfileRequest request) {
        UserEntity user = userRepository.findByIdentitySubject(subject)
                .orElseThrow(UserNotFoundException::new);

        user.setDisplayName(request.displayName());
        user.setPhoneNumber(request.phoneNumber());
    }
}
```

Ví dụ này giả định subject trong token được ánh xạ an toàn tới tài khoản nội bộ. Ứng dụng thực tế có thể cần kiểm tra tenant, trạng thái tài khoản và quyền cập nhật trước khi gán. Điểm quan trọng là client không truyền định danh chủ thể để server tin theo; service lấy danh tính từ security context đã xác thực và chỉ gán hai thuộc tính nằm trong DTO.

Tránh các cách viết tiện lợi nhưng nguy hiểm như:

```java
// Không dùng request không tin cậy để cập nhật toàn bộ entity.
objectMapper.updateValue(userEntity, requestBody);

// Không map mọi thuộc tính cùng tên từ request sang entity nhạy cảm.
modelMapper.map(request, userEntity);
```

Mapper tự động vẫn có thể dùng an toàn nếu cấu hình allow-list rõ ràng, bỏ qua các trường còn lại và có test kiểm chứng. Tuy nhiên, với thao tác nhạy cảm, mapping tường minh giúp reviewer nhìn thấy chính xác trường nào có thể thay đổi.

## 10. Bảo vệ object lồng nhau và collection

Mass assignment không chỉ xảy ra ở cấp object ngoài. Request có thể chứa object con hoặc danh sách quan hệ:

```json
{
  "displayName": "An",
  "addresses": [
    {
      "id": "address-owned-by-another-user",
      "isDefault": true,
      "ownerId": "another-user"
    }
  ]
}
```

Nếu service cập nhật toàn bộ graph entity theo JSON, attacker có thể gắn một địa chỉ không thuộc tài khoản, đổi owner hoặc chiếm quan hệ mặc định. Với object lồng nhau, cần:

- Khai báo DTO con chỉ chứa trường được phép cập nhật.
- Truy vấn object con trong phạm vi owner/tenant đã xác minh; không tin ID do client cung cấp.
- Kiểm tra quyền trên từng object con trước khi thay đổi hoặc liên kết.
- Xác định rõ collection được thay thế toàn bộ, thêm phần tử hay cập nhật từng phần tử.
- Giới hạn số phần tử, độ sâu lồng nhau và kích thước payload.
- Không cho client gán các quan hệ nội bộ như `owner`, `tenant`, `createdBy` hoặc quyền truy cập.

Nếu API cho phép thêm địa chỉ mới, request nên mô tả nội dung địa chỉ; server tự gán owner và tenant từ principal. Nếu API cho phép sửa địa chỉ đã có, path hoặc command phải xác định object đích và service phải truy vấn object đó theo quyền của caller.

## 11. PATCH và quyền cập nhật từng thuộc tính

PATCH thường làm mass assignment khó phát hiện hơn vì request chỉ chứa một phần dữ liệu. Cần định nghĩa chính xác ý nghĩa của trường bị bỏ qua, trường mang `null` và trường có giá trị mới.

Ví dụ với JSON Merge Patch, trường bị bỏ qua thường giữ nguyên; trường được gửi `null` có thể mang nghĩa xóa thuộc tính. Nếu ứng dụng không cho phép xóa trường đó, phải từ chối hoặc quy định rõ cách xử lý. Không dùng một DTO nullable rồi mặc định gán tất cả thuộc tính vì trường bị bỏ qua có thể vô tình ghi đè dữ liệu hiện tại thành `null`.

Nếu dùng JSON Patch với các thao tác `add`, `remove`, `replace`, `move` hoặc `copy`, cần allow-list đường dẫn có thể sửa. Không cho phép path như `/role`, `/tenantId`, `/ownerId`, `/balance` hoặc đường dẫn lồng nhau đi tới thuộc tính nội bộ. Với `move` và `copy`, kiểm tra cả đường dẫn nguồn và đích. Sau khi áp dụng patch, validate trạng thái cuối cùng và kiểm tra authorization cho từng thay đổi trước khi lưu trong một transaction phù hợp.

Một endpoint cập nhật hồ sơ có thể chỉ cho phép các path:

```text
/displayName
/phoneNumber
```

Đường dẫn hợp lệ vẫn chưa đủ để cho phép mọi actor sử dụng. Nếu một thuộc tính chỉ được cập nhật bởi nhân viên hỗ trợ hoặc quản trị viên, cần có policy riêng cho actor và thao tác đó.

## 12. Unknown field và versioning của API

Từ chối unknown field giúp hợp đồng chặt chẽ nhưng có thể ảnh hưởng khả năng triển khai client và server độc lập. Ví dụ client mới gửi trường `preferredLanguage` trong khi server cũ chưa hỗ trợ. Nếu server cũ reject unknown field, request sẽ thất bại; nếu ignore, request có thể thành công nhưng ngôn ngữ không được cập nhật.

Để quản lý tương thích:

- Thêm trường tùy chọn theo cách tương thích ngược khi có thể; client cũ không gửi trường mới vẫn hoạt động.
- Chỉ client bắt đầu gửi trường sau khi server hỗ trợ và công bố schema tương ứng.
- Với thay đổi phá vỡ tương thích, dùng version hoặc quy trình rollout có kiểm soát.
- Có thể triển khai server hiểu trường mới trước, sau đó mới phát hành client gửi trường đó.
- Duy trì contract test giữa các phiên bản client/server được hỗ trợ.
- Không nới lỏng validation trên mọi endpoint chỉ để một client mới có thể rollout sớm.

Với dữ liệu bảo mật nhạy cảm, reject unknown field thường là lựa chọn dễ kiểm soát hơn. Với endpoint cần mở rộng có chủ đích, hãy tạo một vùng extension riêng, giới hạn kích thước, kiểu, namespace và quyền sử dụng; không để các thuộc tính extension tự động ánh xạ vào domain entity.

## 13. Kiểm thử schema, polymorphism và mass assignment

Test cần chứng minh cả dữ liệu hợp lệ được chấp nhận lẫn dữ liệu ngoài hợp đồng bị từ chối hoặc bỏ qua đúng chính sách. Bộ kiểm thử cơ bản nên bao gồm:

| Nhóm | Đầu vào kiểm thử | Kết quả mong đợi |
|---|---|---|
| Unknown field | Gửi thêm `isAdmin` vào DTO hồ sơ | Bị từ chối nếu contract strict; nếu policy ignore thì không có thay đổi quyền |
| Nested unknown field | Thêm `ownerId` vào object địa chỉ con | Không thể đổi owner hoặc tenant |
| Duplicate key | Gửi hai khóa `role` hoặc `displayName` trùng tên trong JSON | Parser từ chối theo chính sách duplicate-key |
| Sai kiểu | Gửi object thay cho chuỗi hoặc chuỗi thay cho số | Trả lỗi validation ổn định, không ép kiểu ngoài hợp đồng |
| Polymorphic allow-list | Gửi `kind` không được khai báo | Deserialize thất bại, không khởi tạo subtype ngoài danh sách |
| Polymorphic field mix | Gửi trường của subtype khác cùng với discriminator hiện tại | Bị từ chối theo schema strict hoặc không ảnh hưởng xử lý |
| Mass assignment | Gửi `role`, `tenantId`, `enabled`, `verified` trong request cập nhật hồ sơ | Các trường này giữ nguyên giá trị do server quản lý |
| Object ownership | Gửi ID địa chỉ thuộc người dùng khác | Không thể đọc, sửa hoặc liên kết địa chỉ đó |
| PATCH semantics | Thử bỏ qua trường, gửi `null`, thay giá trị và patch path cấm | Hành vi khớp hợp đồng; path không được phép bị từ chối |
| Version compatibility | Client cũ và mới gửi schema theo phiên bản hỗ trợ | Rollout không làm mất dữ liệu hoặc âm thầm bỏ qua thay đổi quan trọng |

Ngoài unit test cho DTO và deserializer, cần integration test qua HTTP endpoint thực tế. Kiểm tra database sau request để xác nhận các thuộc tính nhạy cảm không đổi; chỉ kiểm tra status code là chưa đủ. Với subtype hoặc patch có side effect, xác minh cả message, event hoặc lời gọi service được tạo ra.

## 14. Logging và phản hồi lỗi

Khi request vi phạm schema, log có thể ghi endpoint, correlation ID, actor đã xác thực, mã lỗi validation và tên trường vi phạm nếu chính sách cho phép. Không ghi toàn bộ payload, token, dữ liệu thanh toán hoặc giá trị cá nhân nhạy cảm chỉ để debug.

Response lỗi nên cho client biết request không hợp lệ và cách sửa ở mức phù hợp, ví dụ:

```json
{
  "code": "UNKNOWN_FIELD",
  "message": "Request contains a field that is not supported.",
  "correlationId": "req-7f31"
}
```

Không phản hồi stack trace, tên class nội bộ, package Java hoặc thông tin cấu hình deserializer. Chi tiết kỹ thuật cần cho điều tra nên được lưu trong log bảo vệ quyền truy cập và đã loại bỏ bí mật.

## 15. Checklist thiết kế request contract an toàn

- [ ] Request DTO chỉ chứa các trường client thực sự cần điều khiển.
- [ ] Unknown field có chính sách reject hoặc ignore rõ ràng theo endpoint.
- [ ] Object lồng nhau và map động có schema, giới hạn và quy tắc riêng.
- [ ] Duplicate key và coercion sai kiểu được xử lý nhất quán.
- [ ] Polymorphic type dùng discriminator cố định và allow-list subtype.
- [ ] Không deserialize class theo tên do client cung cấp hoặc bật default typing rộng cho dữ liệu không tin cậy.
- [ ] Mỗi subtype được validate và kiểm tra quyền theo actor/ngữ cảnh.
- [ ] Request không được gán trực tiếp vào entity hoặc object có thuộc tính nội bộ.
- [ ] Mapping chỉ cập nhật trường được phép; owner, tenant, role và trạng thái nhạy cảm do server kiểm soát.
- [ ] PATCH phân biệt trường vắng mặt, `null` và giá trị mới; JSON Patch giới hạn path.
- [ ] Contract test và integration test kiểm tra cả response lẫn trạng thái dữ liệu sau request.
- [ ] Log và lỗi không làm lộ payload nhạy cảm hoặc chi tiết nội bộ.

## Kết luận

Unknown field, polymorphic type và mass assignment đều liên quan đến việc server diễn giải dữ liệu do client kiểm soát. Hợp đồng API cần đóng cấu trúc ở nơi phù hợp, quy định rõ chính sách trường không biết, giới hạn subtype qua discriminator allow-list và tách request DTO khỏi domain entity. Service tiếp tục xác minh quyền trên object và từng thuộc tính trước khi cập nhật. Khi schema, deserializer, mapper và authorization cùng thực thi một hợp đồng nhất quán, API giảm được nguy cơ client điều khiển kiểu dữ liệu hoặc thuộc tính nằm ngoài quyền hạn của mình.
