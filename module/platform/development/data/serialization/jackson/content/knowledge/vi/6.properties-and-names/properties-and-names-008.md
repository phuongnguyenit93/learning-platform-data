# Phân biệt thuộc tính chỉ đọc và thuộc tính chỉ ghi

## 1. Hai chiều chuyển đổi của Jackson

Jackson chuyển đổi dữ liệu theo hai chiều. Để hiểu đúng thuộc tính chỉ đọc và chỉ ghi, trước hết cần xác định “đọc” và “ghi” đang được nói từ góc nhìn nào:

- **Serialization (tuần tự hóa):** Jackson đọc trạng thái của đối tượng Java rồi ghi ra JSON. Ví dụ: `ObjectMapper.writeValueAsString(account)`.
- **Deserialization (giải tuần tự hóa):** Jackson đọc JSON rồi ghi các giá trị vào đối tượng Java. Ví dụ: `ObjectMapper.readValue(json, Account.class)`.

Trong tài liệu này, “thuộc tính chỉ đọc” nghĩa là Jackson chỉ đọc thuộc tính từ đối tượng để tạo JSON; Jackson không nhận giá trị JSON đầu vào để gán vào thuộc tính đó. “Thuộc tính chỉ ghi” nghĩa là Jackson được phép ghi giá trị từ JSON vào đối tượng nhưng không đọc thuộc tính đó để đưa vào JSON đầu ra.

Đây là quy tắc truy cập theo từng chiều chuyển đổi của Jackson. Nó không phải khái niệm quyền đọc/ghi file, quyền truy cập của người dùng hay cơ chế bảo mật toàn diện của ứng dụng.

## 2. `@JsonProperty.Access` biểu diễn quyền truy cập theo chiều

Jackson cung cấp enum `JsonProperty.Access` để mô tả một thuộc tính được phép tham gia vào chiều nào:

| Giá trị | POJO → JSON (serialization) | JSON → POJO (deserialization) |
|---|---|---|
| `AUTO` | Theo quy tắc phát hiện thuộc tính và cấu hình thông thường | Theo quy tắc phát hiện thuộc tính và cấu hình thông thường |
| `READ_ONLY` | Được đưa ra JSON | Không nhận giá trị từ JSON |
| `WRITE_ONLY` | Không được đưa ra JSON | Nhận giá trị từ JSON |
| `READ_WRITE` | Được đưa ra JSON | Nhận giá trị từ JSON |

Mặc định, nếu không chỉ định `access`, Jackson áp dụng cơ chế phát hiện và ánh xạ thuộc tính thông thường. `AUTO` thể hiện cách xử lý mặc định đó. `READ_WRITE` chỉ rõ rằng cả hai chiều đều được phép.

Tên `READ_ONLY` và `WRITE_ONLY` dễ gây nhầm nếu chỉ đọc chữ “read” hoặc “write” mà không gắn với thao tác của Jackson. Hãy nhớ hai câu sau:

- `READ_ONLY`: Jackson **đọc từ POJO để ghi JSON**; không ghi giá trị JSON đầu vào vào thuộc tính.
- `WRITE_ONLY`: Jackson **ghi giá trị JSON đầu vào vào POJO**; không đọc thuộc tính để ghi nó ra JSON.

Khai báo thường dùng:

```java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private Long id;

@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String password;
```

`@JsonProperty` cũng có thể chỉ định tên JSON bên ngoài bằng `value`, ví dụ `@JsonProperty(value = "account_id", access = JsonProperty.Access.READ_ONLY)`. Tên thuộc tính trong JSON khi đó là `account_id`, còn tên trường Java có thể là `id`.

## 3. Trường hợp sử dụng phổ biến

### Thuộc tính chỉ đọc: dữ liệu do hệ thống tạo hoặc quản lý

Một số giá trị nên xuất hiện trong response để client quan sát nhưng không nên được client đặt trực tiếp trong request tạo hoặc cập nhật tài nguyên. Ví dụ:

- ID do cơ sở dữ liệu hoặc hệ thống cấp phát.
- Thời điểm tạo bản ghi (`createdAt`).
- Trạng thái được quy trình phía máy chủ quyết định (`approvalStatus`).
- Số lần xử lý hoặc thông tin audit do máy chủ quản lý.

Với những trường này, `READ_ONLY` giúp Jackson không nhận giá trị từ JSON đầu vào, đồng thời vẫn cho phép trường xuất hiện trong JSON đầu ra.

### Thuộc tính chỉ ghi: dữ liệu đầu vào không được phản hồi lại

Một số giá trị cần được nhận từ client để xử lý nhưng không nên xuất hiện trong response JSON. Ví dụ:

- Mật khẩu hoặc mật khẩu mới.
- Mã xác thực dùng một lần.
- Token bí mật gửi trong request body.
- Một trường xác minh chỉ dùng trong bước xử lý đầu vào.

Với những trường này, `WRITE_ONLY` cho phép Jackson đưa giá trị vào đối tượng khi đọc request, nhưng loại trường đó khỏi JSON được tạo từ đối tượng.

## 4. Ví dụ đầy đủ: `id` chỉ đọc và `password` chỉ ghi

Xét một lớp `Account` dùng làm ví dụ cho dữ liệu tài khoản. `id` được máy chủ quản lý nên chỉ xuất hiện trong JSON đầu ra. `password` được gửi trong request để xử lý nhưng không được đưa vào JSON đầu ra.

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public class AccessDirectionDemo {

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        // Đối tượng đã có ID do hệ thống cấp và chứa dữ liệu bí mật trong bộ nhớ.
        Account responseAccount = new Account();
        responseAccount.setId(42L);
        responseAccount.setDisplayName("Mai");
        responseAccount.setPassword("internal-secret");

        // POJO -> JSON: id được xuất, password bị loại khỏi JSON.
        String responseJson = mapper.writeValueAsString(responseAccount);
        JsonNode responseTree = mapper.readTree(responseJson);

        if (!responseTree.has("id")) {
            throw new IllegalStateException("READ_ONLY id should be serialized");
        }
        if (responseTree.has("password")) {
            throw new IllegalStateException("WRITE_ONLY password must not be serialized");
        }

        System.out.println("Response JSON: " + responseJson);

        // JSON -> POJO: giá trị id do client gửi không được áp dụng;
        // password được nhận vào đối tượng để tầng xử lý tiếp theo sử dụng.
        String requestJson = """
                {
                  "id": 999,
                  "displayName": "Mai Nguyen",
                  "password": "client-supplied-password"
                }
                """;

        Account requestAccount = mapper.readValue(requestJson, Account.class);

        if (requestAccount.getId() != null) {
            throw new IllegalStateException("READ_ONLY id must not be populated from JSON");
        }
        if (!"client-supplied-password".equals(requestAccount.getPassword())) {
            throw new IllegalStateException("WRITE_ONLY password should be deserialized");
        }
        if (!"Mai Nguyen".equals(requestAccount.getDisplayName())) {
            throw new IllegalStateException("Normal property was not deserialized");
        }

        System.out.println("Request mapping: PASS");
    }

    public static class Account {
        @JsonProperty(access = JsonProperty.Access.READ_ONLY)
        private Long id;

        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        private String password;

        private String displayName;

        public Account() {
        }

        public Long getId() {
            return id;
        }

        public void setId(Long id) {
            this.id = id;
        }

        public String getPassword() {
            return password;
        }

        public void setPassword(String password) {
            this.password = password;
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }
    }
}
```

Đầu ra response có dạng:

```json
{"id":42,"displayName":"Mai"}
```

Thứ tự thuộc tính có thể phụ thuộc vào cấu hình mapper và cách phát hiện thuộc tính; điều cần quan sát là JSON có `id` và không có `password`.

Trong chiều ngược lại, JSON request có cả `id` và `password`. `id` không được gán từ request vì thuộc tính được đánh dấu `READ_ONLY`; `password` được gán vì thuộc tính được đánh dấu `WRITE_ONLY`. `displayName` không chỉ định access nên hoạt động theo quy tắc thông thường ở cả hai chiều.

## 5. Theo dõi từng chiều bằng bảng hành vi

Với lớp `Account` trong ví dụ, có thể dự đoán kết quả như sau:

| Thuộc tính | Access | Khi ghi POJO thành JSON | Khi đọc JSON thành POJO |
|---|---|---|---|
| `id` | `READ_ONLY` | Có thể xuất giá trị hiện tại của đối tượng | Giá trị gửi từ JSON không được áp dụng |
| `password` | `WRITE_ONLY` | Không xuất thuộc tính | Nhận giá trị từ JSON |
| `displayName` | `AUTO` | Xuất theo quy tắc thông thường | Nhận giá trị theo quy tắc thông thường |

Hãy xem `READ_ONLY` và `WRITE_ONLY` là chính sách cho property đã được Jackson nhận diện. Chúng không tự tạo ra một thuộc tính nếu property không được Jackson phát hiện do visibility, naming strategy hoặc cấu hình khác. Trong ví dụ, getter/setter công khai và trường có annotation giúp Jackson nhận diện các thuộc tính rõ ràng.

## 6. Đặt annotation ở field, getter hay setter?

Jackson xây dựng một thuộc tính logic từ các thành phần mà nó phát hiện, chẳng hạn field, getter, setter hoặc tham số constructor. Các thành phần này có thể được hợp nhất thành cùng một property theo tên logic.

Trong ví dụ, annotation được đặt trên field:

```java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String password;
```

Cách này thường dễ đọc vì chính sách truy cập nằm cạnh dữ liệu của thuộc tính. Cũng có thể đặt annotation trên accessor tương ứng:

```java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
public void setPassword(String password) {
    this.password = password;
}
```

Khi chọn vị trí annotation, cần chú ý:

- Field và accessor phải được Jackson xem là cùng một property. Nếu tên field, getter và setter không khớp, naming strategy hoặc annotation đổi tên có thể làm chúng trở thành các property khác nhau.
- Tránh khai báo nhiều annotation mâu thuẫn trên field, getter và setter. Hãy đặt chính sách access tại một vị trí rõ ràng và giữ tên property nhất quán.
- Với Lombok, kiểm tra accessor được sinh ra và vị trí annotation thực sự được áp dụng. Không giả định annotation trên một thành phần sẽ tự động có tác dụng nếu cấu hình visibility hoặc cách sinh mã đã thay đổi.
- Với lớp thư viện bên thứ ba không thể sửa trực tiếp, Jackson Mix-in có thể cung cấp annotation bổ sung mà không cần thay đổi mã nguồn lớp gốc.

## 7. Phân biệt với `@JsonIgnore` và các cơ chế khác

`@JsonIgnore` thường được dùng để bỏ qua một property trong quá trình ánh xạ. Nếu muốn property chỉ tham gia một chiều, `@JsonProperty(access = ...)` thể hiện ý định trực tiếp hơn:

| Cơ chế | Mục đích thường gặp |
|---|---|
| `@JsonIgnore` | Bỏ qua property trong ánh xạ JSON theo cách thông thường ở cả hai chiều |
| `@JsonProperty(access = READ_ONLY)` | Cho phép serialization, không nhận giá trị khi deserialization |
| `@JsonProperty(access = WRITE_ONLY)` | Nhận giá trị khi deserialization, không đưa ra khi serialization |
| `@JsonView` | Chọn nhóm thuộc tính được hiển thị theo view đang dùng |
| DTO riêng cho request/response | Định nghĩa mô hình dữ liệu đầu vào và đầu ra độc lập |

`@JsonIgnoreProperties` có các tùy chọn `allowGetters` và `allowSetters` cho một số thiết kế tương thích cũ: `allowGetters` cho phép lấy giá trị qua getter trong khi property bị bỏ qua theo hướng còn lại; `allowSetters` cho phép setter nhận giá trị. Với một property cụ thể cần chính sách một chiều, `JsonProperty.Access` thường dễ hiểu hơn.

Không nên dùng `@JsonIgnore` một cách máy móc cho trường mật khẩu nếu API cần nhận mật khẩu từ request. Nếu bỏ qua cả hai chiều, Jackson có thể không đưa mật khẩu vào đối tượng khi giải tuần tự hóa.

## 8. READ_ONLY không thay thế kiểm tra dữ liệu và quyền nghiệp vụ

Đánh dấu `id` là `READ_ONLY` giúp ngăn Jackson áp dụng giá trị `id` từ JSON theo cấu hình property. Tuy nhiên, điều đó không có nghĩa mọi đường đi trong ứng dụng đều không thể thay đổi ID. Mã Java khác vẫn có thể gọi setter, repository có thể gán ID, hoặc một mapper khác có thể dùng cấu hình khác.

Với dữ liệu do máy chủ quản lý, tầng nghiệp vụ vẫn cần quyết định ai được phép tạo, cập nhật hoặc chuyển trạng thái. Không dựa duy nhất vào annotation để thực thi phân quyền.

Tương tự, `WRITE_ONLY` chỉ kiểm soát việc Jackson đưa property vào JSON đầu ra. Nó không mã hóa giá trị, không băm mật khẩu và không xóa bí mật khỏi bộ nhớ. Nếu `password` được nhận vào đối tượng, giá trị vẫn tồn tại trong bộ nhớ cho đến khi được xử lý hoặc giải phóng theo vòng đời đối tượng.

Đối với mật khẩu, quy trình thường cần:

1. Nhận mật khẩu qua thuộc tính đầu vào được đánh dấu `WRITE_ONLY`.
2. Kiểm tra độ dài, chính sách mật khẩu và các điều kiện nghiệp vụ.
3. Băm bằng thuật toán chuyên dụng cho mật khẩu như Argon2id, bcrypt hoặc scrypt qua thư viện đáng tin cậy.
4. Chỉ lưu hash; không lưu mật khẩu dạng rõ.
5. Không đưa mật khẩu hoặc hash nhạy cảm vào log, thông báo lỗi hay response.

Nếu mô hình domain chứa nhiều trường nhạy cảm hoặc có vòng đời khác biệt giữa request và response, DTO riêng thường dễ kiểm soát hơn một entity dùng chung cho mọi chiều.

## 9. Ảnh hưởng của cấu hình deserialization

Các feature khác của mapper có thể ảnh hưởng cách xử lý property bị giới hạn chiều truy cập. Ví dụ, Jackson có `DeserializationFeature.FAIL_ON_IGNORED_PROPERTIES`. Khi được bật, việc JSON cung cấp một property mà cấu hình đánh dấu bỏ qua trong chiều deserialization có thể trở thành lỗi thay vì âm thầm bỏ qua.

Ví dụ cấu hình:

```java
ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_IGNORED_PROPERTIES)
        .build();
```

Do đó, nếu API nhận một trường `id` dù `id` là `READ_ONLY`, hãy xác định rõ chính sách mong muốn:

- Bỏ qua giá trị client gửi và tiếp tục xử lý request; hoặc
- Từ chối request vì client đã gửi một trường chỉ đọc.

Chính sách thứ hai có thể hữu ích khi muốn phát hiện client gửi nhầm hoặc cố ghi vào trường do máy chủ quản lý. Hãy thử nghiệm với cấu hình mapper thực tế của ứng dụng, vì bật feature này có thể thay đổi hành vi của các property bị bỏ qua khác.

Ngoài ra, `FAIL_ON_UNKNOWN_PROPERTIES` và `FAIL_ON_IGNORED_PROPERTIES` giải quyết hai tình huống khác nhau. Thuộc tính không biết là property Jackson không nhận diện được; thuộc tính bị ignored là property đã được nhận diện nhưng bị cấu hình bỏ qua trong ngữ cảnh hiện tại. Không nên xem hai feature này là tương đương.

## 10. Khi nào nên tách DTO request và response?

`READ_ONLY` và `WRITE_ONLY` rất tiện khi một mô hình có phần lớn thuộc tính chung và chỉ một vài trường cần giới hạn chiều. Tuy nhiên, một lớp duy nhất có thể trở nên khó hiểu khi request và response khác nhau đáng kể.

Ví dụ, API tài khoản có thể dùng:

```java
public class CreateAccountRequest {
    private String displayName;
    private String password;
    // getters/setters
}

public class AccountResponse {
    private Long id;
    private String displayName;
    // getters/setters
}
```

Với thiết kế này, request không có trường `id`, còn response không có trường `password`. Mô hình kiểu Java tự thể hiện dữ liệu được phép đi vào và đi ra. Điều đó giúp giảm nguy cơ vô tình đưa một trường nội bộ vào response khi lớp domain được mở rộng.

Có thể chọn cách thiết kế theo quy mô:

- Dùng `JsonProperty.Access` khi property cần dùng chung một lớp nhưng có hướng JSON rõ ràng.
- Dùng DTO riêng khi request và response có mục đích, quy tắc validation hoặc tập trường khác nhau đáng kể.
- Dùng `JsonView` khi cần một số góc nhìn serialization khác nhau trên cùng mô hình và nhóm view được quản lý rõ.

## 11. Tổng kết cách đọc tên access

Khi gặp `@JsonProperty(access = ...)`, hãy quy chiếu trực tiếp vào hai phép chuyển đổi:

```text
POJO  -------------------->  JSON
       serialization
       Jackson đọc property
       READ_ONLY: được phép
       WRITE_ONLY: bị ẩn

JSON  -------------------->  POJO
       deserialization
       Jackson ghi property
       READ_ONLY: không nhận
       WRITE_ONLY: được phép
```

`READ_ONLY` phù hợp với ID hoặc metadata do hệ thống quản lý nhưng vẫn cần xuất hiện trong response. `WRITE_ONLY` phù hợp với mật khẩu hoặc dữ liệu đầu vào không được phản hồi lại. Khi sử dụng, hãy kiểm tra cả hai chiều bằng ví dụ JSON cụ thể, hiểu rõ cấu hình lỗi cho property bị bỏ qua và giữ validation, phân quyền, bảo vệ bí mật ở đúng tầng của ứng dụng.
