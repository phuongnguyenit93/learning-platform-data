# Mẫu tên trường và các quy tắc so khớp theo phiên bản trong Spring DataBinder

Trong Spring Framework, `DataBinder` (và `WebDataBinder` ở tầng web) chuyển dữ liệu đầu vào thành các thuộc tính trên một đối tượng Java. Vì tên trường thường đến từ request không tin cậy, binder có thể được cấu hình để **chỉ nhận những đường dẫn thuộc tính được phép** bằng `setAllowedFields(...)` hoặc loại trừ một số đường dẫn bằng `setDisallowedFields(...)`.

Câu hỏi không đơn thuần là “ghi `firstName` vào bean như thế nào”, mà còn là:

- `address.city` có được xem là cùng loại với `address.*` không?
- `items[0].name` và `attributes[color]` khớp với mẫu nào?
- `name` có khớp `Name` không?
- Nếu một tên trường vừa thuộc allowlist vừa thuộc denylist thì quy tắc nào thắng?
- Các phiên bản Spring khác nhau có thay đổi cách so khớp hay có bản vá bảo mật nào liên quan?

Đây là phần kiến thức về **mẫu tên trường và quy tắc so khớp trong property/setter binding**. Bài phân biệt hành vi API, các thay đổi theo phiên bản, đường dẫn nested/indexed/Map, ví dụ chạy được và các cách kiểm thử. Không đánh đồng cơ chế này với JSON `@RequestBody` hoặc constructor binding.

## 1. Tên trường thực tế là một property path

Một field name truyền cho `DataBinder.bind(PropertyValues)` có thể là tên property đơn giản hoặc một **đường dẫn thuộc tính** (property path):

| Field name | Đối tượng minh họa | Ý nghĩa |
| --- | --- | --- |
| `name` | `ProfileForm.name` | Một thuộc tính bean cấp cao nhất |
| `address.city` | `ProfileForm.address.city` | Thuộc tính `city` của object con `address` |
| `contacts[0].email` | `List<Contact> contacts` | Thuộc tính `email` của phần tử danh sách ở index 0 |
| `preferences[theme]` | `Map<String, String> preferences` | Entry ứng với Map key `"theme"` |
| `preferences['display.name']` | `Map<String, String> preferences` | Map key chứa dấu chấm; cú pháp có nháy giúp giữ ý nghĩa key |
| `orders[2].lines[0].sku` | Cấu trúc lồng nhau | Truy cập theo nhiều mức danh sách và bean |

Các mẫu của `setAllowedFields(...)` và `setDisallowedFields(...)` áp dụng lên **tên đường dẫn thuộc tính đầu vào**, không phải một tập quyền theo tên lớp Java. Để viết policy chính xác, cần liệt kê đường dẫn mà client thực sự gửi, kể cả ngoặc vuông và dấu chấm.

Ví dụ, `address.city` là một field path, còn `address.*` là mẫu bao phủ nhiều đường dẫn bắt đầu bằng `address.`. `attributes[color]` đi vào một Map key; nó không tương đương với `attributes.color`, thường biểu thị truy cập thuộc tính lồng nhau.

### Điều gì được kiểm tra trước khi gán?

Luồng property binding rút gọn:

~~~text
Request field names + values
            |
            v
  DataBinder.bind(...)
            |
   Chuẩn hóa tên đường dẫn
            |
   So khớp allowedFields
   và disallowedFields
            |
       +----+----+
       |         |
  Không cho   Được phép
       |         |
  suppression   Truy cập bean, chuyển kiểu, gán
       |         |
       +----+----+
            |
            v
     BindingResult
       - errors (conversion/validation)
       - suppressed fields
~~~

**Được phép bind không có nghĩa đầu vào hợp lệ.** Một field có thể qua được allowlist nhưng vẫn thất bại vì không thể chuyển sang `Integer`, hoặc vi phạm validation. Ngược lại, một field bị suppression có thể không làm `BindingResult.hasErrors()` thành `true`. Hai loại kết quả cần được xét riêng.

## 2. Cú pháp mẫu: exact match và wildcard `*`

`DataBinder` hỗ trợ các mẫu đơn giản, dựa trên cơ chế so khớp tương tự `PatternMatchUtils.simpleMatch`:

- **Tên chính xác**: `"name"` chỉ khớp tên `name`.
- **Wildcard ở cuối**: `"address*"` khớp tên bắt đầu bằng `address`.
- **Wildcard ở đầu**: `"*Address"` khớp tên kết thúc bằng `Address`.
- **Wildcard ở giữa**: `"address*city"` khớp tên bắt đầu bằng `address` và kết thúc bằng `city`.
- **Nhiều wildcard**: `"orders[*].lines[*].sku"` là một mẫu văn bản có nhiều `*`, có thể bao phủ nhiều chỉ số trong path.

Dấu `*` khớp **không hoặc nhiều ký tự**, không bị giới hạn ở một segment giữa dấu chấm hay một Map key. Cần lưu ý rằng đây **không phải regex** và cũng không phải cú pháp glob của hệ điều hành.

| Mẫu cấu hình | Tên đầu vào | Trong Spring 6.2.x, khớp allowlist? | Giải thích |
| --- | --- | --- | --- |
| `name` | `name` | Có | Exact match |
| `name` | `Name` | Không | `allowedFields` phân biệt chữ hoa/chữ thường |
| `name*` | `name` | Có | `*` có thể khớp chuỗi rỗng |
| `name*` | `nameSuffix` | Có | Bất kỳ phần đuôi nào |
| `address.*` | `address.city` | Có | `*` khớp `city` |
| `address.*` | `address.zipCode` | Có | `*` khớp `zipCode` |
| `address.*` | `address` | Không | Thiếu dấu chấm trong tên |
| `items[*].sku` | `items[0].sku` | Có | Dấu `*` bao phủ `0` |
| `attributes[*]` | `attributes[theme]` | Có | Dấu `*` bao phủ Map key |
| `attributes[color]` | `attributes[size]` | Không | Khác khóa Map |
| `*Address` | `billingAddress` | Có | Khớp phần đuôi |
| `address*city` | `address.contact.city` | Có | Wildcard có thể bao gồm cả dấu chấm |

Các dòng trên mô tả **kết quả so khớp tên**, chưa bảo đảm target thực sự có thuộc tính tương ứng hay chuyển kiểu thành công. Ví dụ `address.contact.city` qua được `address*city` nhưng nếu model không có `contact` thì binder vẫn có thể bỏ qua field không biết hoặc báo lỗi, tùy cấu hình.

### Những cú pháp không phải mẫu của `DataBinder`

Không coi `?`, `[0-9]`, `\d+`, `{one,two}` hay `**` theo quy tắc glob phân đoạn là các toán tử riêng của `DataBinder`. Cơ chế mặc định chủ yếu xử lý `*` cùng so sánh văn bản; ví dụ `items[0-9]` sẽ không tự có nghĩa “chỉ số từ 0 đến 9” như regex. Chuỗi `**` không tự tạo đặc quyền “đúng hai cấp đường dẫn”.

Nếu policy cần kiểm tra tên key chỉ gồm chữ cái hoặc chỉ số nằm trong khoảng, đừng dựa vào wildcard. Hãy kiểm tra bổ sung trong code, ví dụ validation của từng key, độ dài và số lượng entry, hoặc thiết kế DTO chỉ chứa những trường cần thiết.

### Cảnh báo về wildcard quá rộng

~~~java
binder.setAllowedFields("name", "address*");
~~~

`address*` có thể rộng hơn `address.city` và `address.zipCode` nhiều, vì nó có thể bao phủ **mọi field bắt đầu bằng chuỗi `address`**, kể cả tên khác mà ứng dụng không dự định cho phép. Nếu chỉ cần hai trường, viết cụ thể:

~~~java
binder.setAllowedFields("name", "address.city", "address.zipCode");
~~~

Với Map, `preferences[*]` cho phép nhiều khóa khác nhau; đó không phải danh sách hữu hạn. Nếu chỉ cho phép `theme` và `language`, ưu tiên `"preferences[theme]"` và `"preferences[language]"`, sau đó vẫn validate giá trị.

## 3. Hai quy tắc chính: allowlist và denylist

### 3.1. `setAllowedFields(...)`

~~~java
binder.setAllowedFields(
        "name",
        "address.city",
        "preferences[theme]");
~~~

Ý nghĩa: trong **property binding** của binder này, chỉ những field name khớp ít nhất một pattern đã đăng ký mới đi tiếp tới bước gán.

- Khi không cấu hình allowlist, mặc định binder có thể xem mọi field là được phép về mặt tên, tùy những ràng buộc khác.
- Khi đã cung cấp danh sách **không rỗng**, field không khớp bất kỳ pattern nào sẽ bị loại khỏi tập property values cần gán.
- **Matching của allowlist phân biệt hoa/thường** trong các phiên bản Spring được tài liệu hóa ở đây, bao gồm 6.2.x.
- Gọi `setAllowedFields()` với danh sách rỗng không phải cách tin cậy để hiểu là “chặn tất cả”: bộ lọc mặc định kiểm tra danh sách có phần tử trước khi áp dụng. Nếu muốn tắt setter binding, dùng `setDeclarativeBinding(true)` với cách cấu hình phù hợp hoặc DTO/constructor binding.

Ví dụ: pattern `"name"` cho phép field `name`, nhưng không khớp `Name`. **Kết quả của policy matcher và việc JavaBean có property với cách viết hoa nào là hai vấn đề riêng**; test tên thực tế vẫn cần thiết.

### 3.2. `setDisallowedFields(...)`

~~~java
binder.setDisallowedFields(
        "role",
        "account.ownerId");
~~~

Đây là denylist: các field name khớp pattern bị chặn. Ở các bản Spring đã được vá thích hợp, denylist so khớp **không phân biệt hoa/thường**. Tuy nhiên, hành vi này đã có các lỗi bảo mật trong lịch sử phiên bản (mục 5); vì vậy không nên suy ra chỉ nhìn tên API mà hệ thống cũ chắc chắn đã an toàn.

Denylist có rủi ro bảo trì: khi model có thêm property nhạy cảm mới, danh sách chặn có thể không được cập nhật. Spring Framework **7.1 đánh dấu `setDisallowedFields` là deprecated**; định hướng thay thế là DTO chuyên cho input, constructor binding hoặc allowlist rõ ràng.

### 3.3. Khi một field khớp cả hai danh sách

Trong `DataBinder` mặc định:

~~~text
Một tên field đi vào:
  (1) Nếu có allowedFields và KHÔNG khớp -> CHẶN.
  (2) Nếu khớp disallowedFields -> CHẶN.
  (3) Chỉ khi vượt qua cả hai bước -> CÓ THỂ BIND.
~~~

Ví dụ:

~~~java
binder.setAllowedFields("name", "role");
binder.setDisallowedFields("role");
~~~

Field `role` khớp allowlist, nhưng **vẫn bị denylist chặn**. Field `name` qua được cả hai điều kiện. Trong bảng logic:

| Khớp allowedFields (khi có allowlist) | Khớp disallowedFields | Kết luận |
| --- | --- | --- |
| Có | Không | Được phép đi tới binding |
| Không | Không | Bị chặn vì ngoài allowlist |
| Có | Có | Bị chặn; denylist thắng |
| Không | Có | Bị chặn |
| Không có allowlist | Không có denylist | Mặc định không hạn chế bằng hai danh sách |

Quy tắc này áp dụng cho cơ chế `DataBinder.isAllowed(field)` mặc định. Nếu ứng dụng subclass binder và **override `isAllowed`**, phải đọc logic override trước khi kết luận. Đặc biệt với ứng dụng đã tồn tại lâu, custom binder có thể vô tình bỏ qua quy tắc bảo vệ.

## 4. Canonicalization: cùng một key có thể có nhiều cách viết

Spring chuẩn hóa tên property path trước một số bước kiểm tra. Ví dụ trong cú pháp của `BeanWrapper`, hai cách viết khóa Map:

~~~text
preferences[theme]
preferences['theme']
~~~

thường được hiểu là cùng đường dẫn Map entry sau quá trình chuẩn hóa tên property. Tuy nhiên, **cách parser/canonicalizer diễn giải những chuỗi phức tạp có thể thay đổi theo phiên bản**, nên không dựa vào giả định “mọi biến thể tên khác nhau sẽ luôn được chuẩn hóa như nhau”.

Khi tạo allowlist:

~~~java
binder.setAllowedFields("preferences[theme]");
~~~

hãy test với cả dạng field name mà giao diện thực sự gửi, nhất là form có Map key chứa dấu chấm, ngoặc hoặc nháy. Nếu dự án chuyển từ Spring 6.x sang 7.1+, cần chú ý rằng Spring 7.1 giới thiệu bộ phân tích `PropertyPath` nghiêm ngặt hơn thay cho một số API cũ liên quan đến property accessor. **Đừng sao chép một kết quả test property path bất thường ở phiên bản cũ rồi coi đó là hợp đồng vĩnh viễn.**

Các trường hợp nên xem xét riêng:

- `address.city` so với `address['city']`: một bên là thuộc tính lồng nhau, một bên có thể là Map key theo kiểu dữ liệu đích.
- `preferences[theme]` so với `preferences['theme']`: cách diễn đạt key Map.
- `items[0].sku` so với `items[00].sku`: string path, chỉ số collection, canonicalization và truy cập kiểu đích có thể tương tác.
- `name` so với `Name`: quy tắc phân biệt hoa/thường của allowedFields; không đánh đồng với chuẩn hóa ngoặc Map.
- Các key chứa ký tự đặc biệt: nên xét giới hạn contract và test trên đúng thư viện đang triển khai.

Tính an toàn nên đến từ **contract input hẹp**, allowlist và quyền nghiệp vụ, không phải việc cố đoán hết mọi biến thể văn bản có thể gửi.

## 5. Các thay đổi theo phiên bản Spring cần biết

Đây là phần rất quan trọng vì tài liệu hoặc bài blog viết cho một patch version cũ có thể mô tả hành vi khác với phiên bản đang dùng.

### 5.1. Sự khác biệt về case sensitivity

Ở các phiên bản Spring hiện đại đã vá, tài liệu `DataBinder.isAllowed` mô tả:

- `allowedFields`: **case-sensitive**, ví dụ `"name"` không khớp `"Name"`.
- `disallowedFields`: **case-insensitive**, ví dụ `"role"` chặn cả `"role"` và những cách viết hoa/thường khác.
- Nếu cả hai danh sách khớp thì **disallowed thắng**.

Tuy nhiên, không phải mọi patch release cũ đều triển khai denylist với độ tin cậy như nhau. Lịch sử các bản vá cho thấy việc viết chính xác tên field đặc biệt quan trọng.

### 5.2. Dòng thời gian các bản vá liên quan `disallowedFields`

| Thời điểm / advisory | Những phiên bản bị ảnh hưởng theo Spring | Bản sửa được công bố | Ý nghĩa |
| --- | --- | --- | --- |
| 2022 — `CVE-2022-22968` | Spring 5.3.0–5.3.18; 5.2.20 trở về trước | **5.3.19; 5.2.21** | Denylist trước đó so khớp phân biệt hoa/thường; bản vá chuyển theo hướng case-insensitive |
| 2024 — `CVE-2024-38820` | 5.3.40 trở về trước; 6.0.0–6.0.24; 6.1.0–6.1.13 | **5.3.41; 6.0.25; 6.1.14** | Sửa trường hợp lowercasing phụ thuộc `Locale` gây ngoại lệ so khớp denylist |
| 2025 — `CVE-2025-22233` | 5.3.42 trở về trước; 6.0.0–6.0.27; 6.1.0–6.1.19; 6.2.0–6.2.6 | **5.3.43; 6.0.28; 6.1.20; 6.2.7** | Xử lý tiếp các tình huống có thể vượt qua kiểm tra denylist |

Nguồn cho các mốc trên là **trang Security Advisories chính thức của Spring**, có liên kết ở cuối bài. Đây là **các mốc sửa từng vấn đề đã công bố**, không phải khẳng định rằng chỉ cần tới đúng bản đó thì mọi lỗ hổng Spring khác đã được xử lý. Khi triển khai thực tế, dùng một patch version còn được hỗ trợ và cập nhật advisory mới nhất của **nhánh đang sử dụng**.

Đặc biệt: việc tài liệu 6.0 hoặc 6.1 nói `disallowedFields` là case-insensitive **không đảm bảo** mọi bản 6.0.x/6.1.x cũ đã xử lý đầy đủ các trường hợp đặc biệt. Chính các advisory 2024 và 2025 lý giải vì sao kiểm thử trên **phiên bản chính xác** là bắt buộc.

### 5.3. Spring 6.1+: `declarativeBinding`

Từ Spring Framework **6.1**, `DataBinder` hỗ trợ `setDeclarativeBinding(true)` để hạn chế binding theo hợp đồng đã khai báo:

- **Constructor binding** qua `construct(...)` được áp dụng cho những tham số constructor mà ứng dụng xác định.
- **Setter/property binding** chỉ được thực hiện khi có cấu hình `allowedFields` tương ứng.

Ví dụ ở mức binder:

~~~java
DataBinder binder = new DataBinder(input, "input");
binder.setDeclarativeBinding(true);
binder.setAllowedFields("name", "address.city");
~~~

Ở cấu hình này, nếu đường bind là setter/property binding, các field đã chỉ định được phép gán. Nếu dự định **chỉ constructor binding**, không nên vô tình cấu hình wildcard setter quá rộng. Lưu ý `setAllowedFields` và `setDisallowedFields` là cơ chế lọc cho **property binding với `bind(PropertyValues)`**, không phải bộ lọc tương tự áp dụng sau `construct(...)`.

### 5.4. Spring Framework 7.1: deprecation và parser

Trong Spring **7.1**, `disallowedFields` được đánh dấu **deprecated** vì khó duy trì và dễ bỏ sót khi mô hình dữ liệu phát triển. Đồng thời, Spring giới thiệu `PropertyPath` và parser chặt chẽ hơn cho tên đường dẫn bean. Điều này không làm `setAllowedFields` mất ý nghĩa; ngược lại, cấu hình allowlist hoặc input DTO riêng tiếp tục là cách rõ ràng để hạn chế trường có thể sửa.

Khi nâng cấp lên 7.1, cần rà soát:

1. Có đang gọi `setDisallowedFields` hoặc `getDisallowedFields` và phát sinh cảnh báo deprecation không?
2. Có override `isAllowed(...)`, `setAllowedFields(...)` hoặc logic chuẩn hóa path không?
3. Có field name đặc biệt, Map key phức tạp hoặc mẫu wildcard quá rộng không?
4. Có thể chuyển sang constructor/record DTO hoặc `setDeclarativeBinding(true)` thay cho denylist không?
5. Test cùng request ở cả phiên bản cũ và mới có cho phép đúng tập field mong đợi không?

**Không gộp tất cả các bản vá 2022–2025 thành một quy tắc “bắt đầu từ Spring 6 thì luôn an toàn”.** Chọn đúng nhánh, đúng patch version và test thực tế.

## 6. Chương trình Java 17+ minh họa cách khớp mẫu trên Spring 6.2.7

Chương trình sau dùng **Spring Framework 6.2.7**, là mốc đã có bản sửa `CVE-2025-22233` trong nhánh 6.2. Đây là **phiên bản cố định để tái hiện bài học**, không phải khuyến nghị giữ nguyên bản này cho hệ thống production. Khi triển khai production, cần cập nhật bản vá mới được hỗ trợ.

Chương trình kiểm tra ba tình huống:

1. **exact** — allowlist từng trường cụ thể, bao gồm nested field và Map key; thử gửi `Name` khác chữ hoa và `role` không cho phép.
2. **wildcard** — mở rộng allowlist qua `address.*` và `prefs[*]`; chứng minh wildcard có thể cho phép thêm Map key không dự định.
3. **deny** — ví dụ tham khảo denylist case-insensitive và ưu tiên chặn ngay cả khi allowlist là `*`; **không khuyến nghị** dùng denylist rộng này như policy bảo mật production.

### 6.1. Cấu trúc dự án

~~~text
spring-field-patterns/
├── pom.xml
└── src/main/java/example/FieldPatternDemo.java
~~~

### 6.2. Tệp `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-field-patterns</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.FieldPatternDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.3. Tệp `FieldPatternDemo.java`

~~~java
package example;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public class FieldPatternDemo {

    public static class Address {
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class ProfileForm {
        private String name;
        private Address address = new Address();
        private Map<String, String> prefs = new LinkedHashMap<>();
        private String role = "USER";

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }

        public Map<String, String> getPrefs() {
            return prefs;
        }

        public void setPrefs(Map<String, String> prefs) {
            this.prefs = prefs;
        }

        public String getRole() {
            return role;
        }

        public void setRole(String role) {
            this.role = role;
        }
    }

    private static void run(
            String label,
            Map<String, String> incoming,
            String[] allowed,
            String[] disallowed) {

        ProfileForm form = new ProfileForm();
        DataBinder binder = new DataBinder(form, "profile");

        if (allowed != null) {
            binder.setAllowedFields(allowed);
        }
        if (disallowed != null) {
            binder.setDisallowedFields(disallowed);
        }

        binder.bind(new MutablePropertyValues(incoming));
        BindingResult result = binder.getBindingResult();

        String[] blocked = result.getSuppressedFields();
        Arrays.sort(blocked); // Bảo đảm thứ tự stdout.

        System.out.println(label
                + " name=" + form.getName()
                + ", city=" + form.getAddress().getCity()
                + ", theme=" + form.getPrefs().get("theme")
                + ", secret=" + form.getPrefs().get("secret")
                + ", role=" + form.getRole());

        System.out.println(label
                + " errors=" + result.getErrorCount()
                + ", suppressed=" + Arrays.toString(blocked));
    }

    public static void main(String[] args) {
        Map<String, String> request = new LinkedHashMap<>();
        request.put("name", "Lan");
        request.put("Name", "WrongCase");
        request.put("address.city", "Hue");
        request.put("prefs[theme]", "dark");
        request.put("prefs[secret]", "hidden");
        request.put("role", "ADMIN");

        run("exact", request,
                new String[] {
                    "name", "address.city", "prefs[theme]"
                },
                null);

        run("wildcard", request,
                new String[] {
                    "name", "address.*", "prefs[*]"
                },
                null);

        Map<String, String> denyRequest = new LinkedHashMap<>();
        denyRequest.put("name", "Lan");
        denyRequest.put("role", "ADMIN");
        denyRequest.put("ROLE", "ROOT");

        run("deny", denyRequest,
                new String[] { "*" },
                new String[] { "role" });
    }
}
~~~

### 6.4. Chạy và quan sát

Yêu cầu **JDK 17+** và Maven; lần chạy đầu có thể cần Internet để tải dependency từ Maven Central:

~~~bash
mvn -q compile exec:java
~~~

Kết quả mong đợi:

~~~text
exact name=Lan, city=Hue, theme=dark, secret=null, role=USER
exact errors=0, suppressed=[Name, prefs[secret], role]
wildcard name=Lan, city=Hue, theme=dark, secret=hidden, role=USER
wildcard errors=0, suppressed=[Name, role]
deny name=Lan, city=null, theme=null, secret=null, role=USER
deny errors=0, suppressed=[ROLE, role]
~~~

**Giải thích `exact`:**

- `name`, `address.city` và `prefs[theme]` khớp allowlist, nên được gán.
- `Name` không khớp `name` theo quy tắc case-sensitive và bị suppression.
- `prefs[secret]` không được liệt kê; `role` cũng không. Cả hai bị chặn trước bước gán.
- `role` giữ giá trị khởi tạo `"USER"`; `prefs.get("secret")` vẫn là `null`.
- `getErrorCount()` có thể bằng 0 dù đã có các field bị suppression.

**Giải thích `wildcard`:**

- `address.*` cho phép `address.city`.
- `prefs[*]` không chỉ cho phép `prefs[theme]` mà còn cho phép `prefs[secret]`.
- `role` và `Name` vẫn bị chặn. Đây là lý do wildcard cần được coi là **mở rộng quyền ghi**.
- Mẫu trên cho thấy wildcard khớp **tên**, không tự validate nội dung của Map key `secret`.

**Giải thích `deny`:**

- Allowlist `*` cho phép về mặt mẫu tên rất rộng.
- Denylist `role` của Spring 6.2.7 chặn cả `role` và `ROLE` trong ví dụ này, nên không có cái nào được gán.
- Ứng dụng không nên áp dụng `*` cùng một vài dòng denylist rồi coi đó là kiểm soát bảo mật đủ mạnh. Đây chỉ là ví dụ đối chiếu thứ tự và case sensitivity.

Chương trình sử dụng `Arrays.sort(blocked)` vì không nên phụ thuộc thứ tự nội bộ của danh sách field bị suppression khi in test. Nó cũng cố ý không đăng ký validator để tách **kết quả filter field name** khỏi lỗi chuyển đổi hoặc validation.

## 7. Đọc suppressed fields: bị chặn không nhất thiết là lỗi bind

Sau `binder.bind(...)`, hãy đọc:

~~~java
BindingResult result = binder.getBindingResult();
String[] suppressed = result.getSuppressedFields();

if (suppressed.length > 0) {
    // Ứng dụng quyết định: từ chối, ghi nhận hoặc bỏ qua.
}
~~~

`getSuppressedFields()` liệt kê những field bị binder chặn bởi chính sách cho phép/không cho phép trong property binding. Các field này đã bị loại khỏi tập đầu vào được gán. **Sự tồn tại của suppressed field không nhất thiết tạo `FieldError`**, do đó:

~~~java
if (!result.hasErrors()) {
    // Chưa đủ để kết luận rằng không có field bị chặn.
}
~~~

Một chính sách tương đối chặt ở ranh giới API:

~~~java
if (result.hasErrors()
        || result.getSuppressedFields().length > 0) {
    // Trả response lỗi và không gọi service thay đổi dữ liệu.
    return;
}
~~~

Đây là **đoạn code minh họa bên trong một phương thức `void`**. Hành vi từ chối suppressed fields là **lựa chọn của ứng dụng** chứ không phải quy tắc tự động do Spring bắt buộc. Với vài giao diện có field bổ sung hợp lệ, ứng dụng có thể chọn bỏ qua và ghi log; cần định nghĩa và kiểm thử contract rõ ràng.

Ngoài suppression, nếu bật `setIgnoreUnknownFields(false)` thì trường không tồn tại trên model có thể gây lỗi binder riêng. **Unknown property**, **suppressed field** và **conversion error** là ba trạng thái khác nhau; chúng không được đánh đồng.

### Trường bị chặn vẫn có thể nằm trong request

Client có thể gửi:

~~~text
name=Lan&role=ADMIN
~~~

Trong `ProfileForm` có `role`, nhưng allowlist chỉ `name`. Khi đó:

- `form.getName()` có thể là `Lan`.
- `form.getRole()` vẫn là `USER`.
- `getSuppressedFields()` có thể chứa `"role"`.
- `hasErrors()` vẫn có thể là `false`.

Dựa mỗi vào target cuối cùng sẽ bỏ lỡ sự kiện client đã cố gửi một trường ngoài contract. Tuy nhiên, **không ghi nguyên dữ liệu đầu vào nhạy cảm vào log**, nhất là mật khẩu, access token hoặc thông tin cá nhân. Thông thường chỉ cần tên field và thông tin ngữ cảnh được phép lưu.

## 8. Tích hợp `WebDataBinder` với Spring MVC

Trong controller xử lý form hoặc query parameter dưới dạng `@ModelAttribute`, có thể cấu hình mẫu:

~~~java
// Đoạn trích trong một @Controller hoặc @ControllerAdvice.
// Cần import các annotation và WebDataBinder của Spring MVC.
@InitBinder("profile")
void configureBinder(WebDataBinder binder) {
    binder.setDeclarativeBinding(true);
    binder.setAllowedFields(
            "name",
            "address.city",
            "prefs[theme]");
}
~~~

Điều này giới hạn **setter/property binding** của đối tượng mang tên `profile` tại điểm áp dụng initializer. Chú ý:

- Tên `"profile"` trong `@InitBinder` là tên model attribute; cần khớp với nơi nhận input.
- Nếu chỉ muốn constructor binding từ record/immutable DTO, có thể dùng `setDeclarativeBinding(true)` mà không mở thêm setter binding.
- Những field phức tạp như `prefs[theme]` cần có object/Map trung gian có thể truy cập phù hợp.
- Nếu controller có nhiều use case với danh sách trường khác nhau, tốt hơn nên có DTO chuyên biệt thay vì một allowlist rộng dùng chung.

Controller mẫu (không chạy độc lập vì cần `profileService`, DTO, MVC config):

~~~java
@PostMapping("/profiles")
public String create(
        @Valid @ModelAttribute("profile") ProfileForm form,
        BindingResult result) {

    if (result.hasErrors()
            || result.getSuppressedFields().length > 0) {
        return "profiles/new";
    }

    profileService.create(form);
    return "redirect:/profiles";
}
~~~

`BindingResult` phải đứng **ngay sau** `@ModelAttribute` tương ứng. `@Valid` chỉ kích hoạt các ràng buộc phù hợp khi có validator/provider được cấu hình. Ví dụ không thể dựa vào allowlist để tự động kiểm tra giá trị city hay theme thuộc tập lựa chọn hợp lệ.

### Form data khác JSON `@RequestBody`

`@InitBinder` cùng các mẫu `allowedFields` áp dụng cho **property binding** của `DataBinder`. Với `@RequestBody` nhận JSON, HTTP message converter (thường Jackson) tạo object qua deserialization; nó **không tự lấy toàn bộ allowedFields và dùng như bộ lọc key JSON**.

Ví dụ JSON:

~~~json
{
  "name": "Lan",
  "role": "ADMIN"
}
~~~

Nếu `@RequestBody` được deserialize trực tiếp vào một entity có setter `setRole`, không thể tự tin rằng chỉ cần khai báo `@InitBinder` với allowedFields là đã chặn được JSON field `role`. Đối với JSON, dùng DTO riêng chỉ chứa trường được phép nhận, cấu hình deserialization phù hợp, validation và ánh xạ có kiểm soát sang domain.

**Đây là ranh giới quan trọng:** một bài test `DataBinder.bind(new MutablePropertyValues(...))` không chứng minh một API `@RequestBody` có cùng hành vi. Hãy kiểm thử cả hai nếu ứng dụng hỗ trợ cả form và JSON.

### Constructor binding không đi qua cùng bộ lọc setter

Spring 6.1+ hỗ trợ `DataBinder.construct(...)` cho constructor binding; các tham số được ràng buộc theo constructor, thay vì duyệt setter/field path theo `setAllowedFields`. Vì vậy:

- Nếu constructor DTO có tham số `role`, đó là một phần input contract của constructor đó.
- Không nên suy luận `setDisallowedFields("role")` sẽ chặn việc cung cấp tham số `role` cho constructor.
- Thiết kế constructor/record DTO chỉ có các trường người dùng thật sự được gửi.
- Với các đối tượng domain có nhiều property đặc quyền, constructor DTO và mapping có kiểm soát thường an toàn hơn setter binding trực tiếp.

## 9. Lập bảng quyết định khi viết allowlist cho dự án

Giả sử form sản phẩm có các trường:

~~~text
title
description
price
shipping.address.city
shipping.address.postalCode
attributes[color]
attributes[size]
inventory.internalCost
ownerId
isPublished
~~~

Chỉ người quản trị mới có quyền sửa `inventory.internalCost`, `ownerId` và `isPublished`. Form dành cho người bán thường:

~~~java
binder.setAllowedFields(
        "title",
        "description",
        "price",
        "shipping.address.city",
        "shipping.address.postalCode",
        "attributes[color]",
        "attributes[size]");
~~~

Các điểm quan trọng:

1. **Ưu tiên exact path** nếu số lượng trường hữu hạn, tránh mở rộng ngoài ý muốn.
2. Khi dùng `shipping.address.*`, hãy tự hỏi tương lai có xuất hiện field `shipping.address.verificationStatus` không. Wildcard sẽ bao phủ cả field mới nếu path khớp.
3. Với `attributes[*]`, kiểm tra cả tên khóa và giá trị vì client có thể bổ sung key mới ngoài dự tính.
4. Tách DTO theo quyền và thao tác, ví dụ `CreateProductForm`, `UpdateProductForm`, `AdminProductForm`; không chỉ dựa vào filter string cho mọi vai trò.
5. Kiểm tra quyền đối với **đối tượng đích** (người dùng có quyền sửa sản phẩm này không?) tại service, ngay cả khi field name đã được phép.
6. Không bind trực tiếp entity chứa trường hệ thống nếu không có lý do và lớp bảo vệ phù hợp.

## 10. Kiểm thử theo phiên bản: không chỉ test trường hợp bình thường

Đối với mỗi ứng dụng nâng cấp Spring, tạo một **ma trận test** thể hiện các tên trường hợp lệ và không hợp lệ. Chạy ma trận đó trên đúng dependency version mà ứng dụng sử dụng.

| Nhóm test | Input field | Policy mẫu | Điều mong đợi |
| --- | --- | --- | --- |
| Exact | `name` | allowed `name` | Được bind |
| Khác hoa/thường | `Name` | allowed `name` | Bị suppression |
| Nested path hợp lệ | `address.city` | allowed `address.city` | Được bind khi model có path |
| Nested không cho phép | `address.postalCode` | allowed `address.city` | Bị suppression |
| Wildcard | `address.city` | allowed `address.*` | Được phép qua filter |
| Map key cụ thể | `prefs[theme]` | allowed `prefs[theme]` | Được phép qua filter |
| Map key khác | `prefs[secret]` | allowed `prefs[theme]` | Bị suppression |
| Map wildcard | `prefs[secret]` | allowed `prefs[*]` | Được phép qua filter; cần validate key |
| Denylist trùng allowlist | `role` | allowed `*`; disallowed `role` | Bị suppression |
| Denylist chữ hoa | `ROLE` | allowed `*`; disallowed `role` | Bị chặn ở bản vá thích hợp |
| Field sai kiểu | `price=abc` | allowed `price` | Qua filter nhưng có thể lỗi `typeMismatch` |
| Field lạ | `unknown=1` | Không giới hạn field | Có thể bị bỏ qua nếu bật ignoreUnknownFields mặc định; không đồng nghĩa suppressed |

Cần test cả **nội dung target sau bind** và **`BindingResult`**:

~~~java
// Đoạn trích trong test JUnit 5 đã cấu hình.
// "form", "binder" và "result" được tạo ở fixture test.
assertEquals("USER", form.getRole());
assertTrue(Arrays.asList(result.getSuppressedFields())
        .contains("role"));
~~~

Không chỉ assert `!result.hasErrors()`: trường bị suppression có thể không sinh `FieldError`. Với phiên bản Spring cũ, nhất là liên quan `disallowedFields`, hãy kiểm thử thêm các biến thể hoa/thường và property path có nested field; điều này hỗ trợ phát hiện vấn đề nhưng **không thay thế việc nâng cấp bản vá bảo mật**.

### Ví dụ ý tưởng parameterized test

Có thể tạo tập dữ liệu:

~~~text
pattern                 field                    expected
"name"                  "name"                   true
"name"                  "Name"                   false
"address.*"             "address.city"           true
"address.*"             "address.zipCode"        true
"prefs[theme]"          "prefs[secret]"          false
"prefs[*]"              "prefs[secret]"          true
~~~

Đây là các trường hợp cho bộ lọc allowlist của `DataBinder` mặc định. Nếu test kết quả **binding thực sự**, phải bảo đảm tất cả tên field dự kiến được phép đều tồn tại trong cấu trúc DTO, nếu không kết quả còn phụ thuộc bước truy cập property. Có thể dùng subclass chỉ để test `isAllowed` khi cần kiểm tra riêng quy tắc protected method, nhưng không nên thay thế integration test binding.

### Kiểm thử khi đổi locale hoặc parser

Đối với đội nâng cấp từ các patch release bị ảnh hưởng:

- Chạy test với locale mặc định không phải English nếu hệ thống từng dựa vào denylist/chuẩn hóa chữ hoa.
- Đối chiếu pattern có nested path và nhiều cách viết Map key ở phiên bản cũ và mới.
- Đảm bảo mọi request chứa field ngoài contract không chạm được thuộc tính nhạy cảm.
- Không kiểm tra chỉ một chuỗi được truyền vào `isAllowed`; cần kiểm tra đường đi qua `bind(...)` và dữ liệu target sau đó.
- Đọc lại advisory chính thức của nhánh Spring đang dùng; trường hợp đã được vá một lần vẫn có thể có advisory tiếp theo.

## 11. Những lỗi thiết kế thường gặp

**Lỗi 1 — Xem pattern như regex.**

~~~java
binder.setAllowedFields("items[0-9].name");
~~~

Đây **không** phải một regex biểu diễn chữ số 0–9. Để cho phép những chỉ số hợp lệ, dùng mẫu phù hợp như `"items[*].name"` rồi thêm ràng buộc chiều dài/giới hạn index và kích thước collection, hoặc thiết kế DTO giới hạn cấu trúc.

**Lỗi 2 — Dùng wildcard để “an toàn cho tương lai”.**

~~~java
binder.setAllowedFields("user*");
~~~

Nếu model xuất hiện `userRole` hoặc `userAdminFlag` về sau, mẫu quá rộng có thể cho phép client cập nhật chúng. Exact allowlist hoặc input DTO hẹp thường an toàn hơn.

**Lỗi 3 — Dùng denylist thay allowlist rồi không nâng cấp Spring.**

~~~java
binder.setDisallowedFields("role", "ownerId");
~~~

Các advisory Spring đã ghi nhận nhiều ngoại lệ so khớp denylist qua phiên bản. Không dùng danh sách chặn như lớp bảo vệ duy nhất khi DTO còn nhiều thuộc tính nhạy cảm. Spring 7.1 cũng đánh dấu API đó deprecated.

**Lỗi 4 — Tưởng allowlist xử lý cả constructor binding.**

`setAllowedFields(...)` áp dụng cho property binding. Với record/constructor, hãy giới hạn constructor arguments của DTO theo contract. Không có nghĩa mọi tên trong request ngoài allowlist đều bị chặn ở tất cả cơ chế nhận dữ liệu.

**Lỗi 5 — Chỉ kiểm tra `BindingResult.hasErrors()`.**

Một field bị suppression có thể không tính là validation error. Cần xem `getSuppressedFields()` theo chính sách ứng dụng, và kiểm tra side effect không được xảy ra với input vi phạm.

**Lỗi 6 — Cấu hình allowlist rỗng để mong chặn mọi trường.**

Với bộ lọc mặc định, danh sách rỗng có thể được hiểu là **không giới hạn**. Nếu mục tiêu là constructor binding only, cấu hình `setDeclarativeBinding(true)` rõ ràng và kiểm thử đường setter không được chạy.

**Lỗi 7 — Bỏ qua đường dẫn nested hoặc Map.**

Chặn `role` không tự chặn mọi trường nhạy cảm như `account.role` hay `permissions[admin]`. Exact DTO và validation phải bao phủ cây object mà request có thể truy cập.

**Lỗi 8 — Dựa vào một bản ghi trong blog cũ.**

Một bài viết trước các bản vá 2022, 2024 hoặc 2025 có thể mô tả case sensitivity khác, hoặc chưa biết ngoại lệ về locale. Khi so sánh, luôn ghi **nhánh + patch version** của Spring.

**Lỗi 9 — Cho rằng `@RequestBody` chịu cùng luật với `@ModelAttribute`.**

JSON deserialization thường qua Jackson, không phải `DataBinder.bind(PropertyValues)` cho từng key field. Hãy dùng DTO cho JSON và cơ chế kiểm soát tương ứng.

**Lỗi 10 — Quên rằng tên trường được phép vẫn cần validation.**

Allowed field `price` có thể chứa `-100`, `abc` hoặc giá trị vượt giới hạn. Field-name policy chỉ bảo vệ **bề mặt ghi thuộc tính**; conversion, Bean Validation, authorization và business rules vẫn cần thiết.

## 12. Checklist nâng cấp và triển khai an toàn

1. **Kiểm kê phiên bản** Spring Framework thực chạy, bao gồm dependency được Spring Boot BOM quản lý; không chỉ nhìn version trong một đoạn tài liệu.
2. **Đọc advisory** của nhánh đang dùng và cập nhật tới patch release được hỗ trợ. Đặc biệt rà soát `CVE-2022-22968`, `CVE-2024-38820`, `CVE-2025-22233` khi ứng dụng có `disallowedFields`.
3. **Ưu tiên DTO input riêng** chỉ chứa các field được phép. Với dữ liệu ổn định, record hoặc constructor DTO giảm diện tích setter binding.
4. Với property binding, khai báo **`setAllowedFields(...)` theo exact path** trước; chỉ dùng wildcard khi thật sự cần và hiểu phạm vi.
5. Dùng **`setDeclarativeBinding(true)`** khi muốn hạn chế rõ constructor/setter binding (Spring 6.1+).
6. Nếu đang có denylist, lập kế hoạch loại bỏ phụ thuộc vào nó; riêng Spring 7.1, chú ý cảnh báo deprecation.
7. **Test case-sensitive allowlist** bằng các biến thể tên, nested path, index và Map key, trên đúng patch version.
8. **Kiểm tra kết quả thực sự**: target đã gán, `BindingResult.hasErrors()`, `getSuppressedFields()` và việc service có bị gọi khi input bị chặn hay không.
9. **Giới hạn độ sâu/kích thước input**, số entry collection, index và key nếu có nested/Map path; tránh để wildcard mở ra cấu trúc không kiểm soát.
10. **Không dựa chỉ vào field-name policy** để phân quyền. Service vẫn phải xác minh người dùng có quyền thay đổi tài nguyên và trạng thái đang được yêu cầu.

### Kết luận

**Mẫu tên trường của `DataBinder` được so khớp trên property path, hỗ trợ exact match và ký tự đại diện `*`.** Trong các Spring 6.x đã vá, `allowedFields` so khớp phân biệt hoa/thường, còn `disallowedFields` được thiết kế so khớp không phân biệt hoa/thường và **denylist thắng nếu đồng thời khớp allowlist**. Tuy nhiên, đã có nhiều thay đổi và bản vá qua các nhánh Spring, nên không thể suy từ phiên bản major rằng mọi trường hợp bảo vệ đã được xử lý.

Cách thiết kế ổn định nhất là **DTO input hẹp + allowlist chính xác khi cần setter binding + validation + authorization + test theo phiên bản**. `disallowedFields` nên được xem như cơ chế tương thích/lịch sử, không phải lựa chọn ưu tiên cho thiết kế mới.

### Tài liệu tham khảo chính thức

- [Spring Framework — Data Binding Model Design, 7.1](https://docs.spring.io/spring-framework/reference/7.1/web/webmvc/mvc-data-binding.html)
- [Spring Framework — Data Binding, BeanWrapper và constructor binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html)
- [Spring 6.2.7 — `DataBinder` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring 6.1 — `setDeclarativeBinding` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 7.1 — Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.1-Release-Notes)
- [Spring Security Advisory — CVE-2022-22968](https://spring.io/security/cve-2022-22968/)
- [Spring Security Advisory — CVE-2024-38820](https://spring.io/security/cve-2024-38820/)
- [Spring Security Advisory — CVE-2025-22233](https://spring.io/security/cve-2025-22233/)
