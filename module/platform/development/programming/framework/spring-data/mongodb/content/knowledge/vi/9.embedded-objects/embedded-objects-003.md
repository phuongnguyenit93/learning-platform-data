# Tên tham số constructor, -parameters và lỗi không khớp dữ liệu

## 1. Vấn đề thực tế: document có dữ liệu nhưng Java không tạo được object

Trong MongoDB, một document có thể chứa nhiều object lồng nhau. Spring Data MongoDB cho phép đọc các object đó thành lớp Java thông qua cơ chế ánh xạ (mapping). Khi lớp Java có constructor nhận tham số, framework phải biết **giá trị BSON nào tương ứng với từng tham số**.

Giả sử trong collection customers có document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  displayName: "Lan",
  address: {
    city: "Đà Nẵng",
    postal_code: "550000"
  }
}
~~~

Nếu lớp Address dùng constructor nhận hai tham số city và postalCode, Spring Data cần xác định:

- Tham số **city** tương ứng với thuộc tính Java **city**, đọc từ field BSON **address.city**.
- Tham số **postalCode** tương ứng với thuộc tính Java **postalCode**, đọc từ field BSON **address.postal_code** nếu khai báo alias bằng @Field.

Nếu thông tin **tên tham số của constructor** không hiện diện trong bytecode hoặc tên tham số không ánh xạ được về các thuộc tính persistent của class, việc tạo object có thể thất bại dù document vẫn hợp lệ về mặt BSON.

Đây là nội dung của bài **Tên tham số constructor, -parameters và lỗi không khớp dữ liệu**, thuộc chương **Đối tượng và nhúng**. Trong module **SPRING_DATA_MONGODB**, hiểu constructor binding là nền tảng để ánh xạ document, thao tác qua MongoTemplate hoặc repository và viết kiểm thử dữ liệu. Các lựa chọn về mapping cũng ảnh hưởng đến truy vấn, aggregation, index, transaction, reactive access và khả năng chẩn đoán lỗi dữ liệu.

Sau bài này, bạn sẽ có thể:

1. Giải thích cách Spring Data MongoDB đọc document nhúng và gắn giá trị vào constructor Java.
2. Sử dụng **javac -parameters** để lưu tên tham số trong bytecode khi cần.
3. Chọn constructor ánh xạ bằng **@PersistenceCreator** và hiểu các trường hợp record/no-args constructor.
4. Phân biệt **tên tham số Java**, **tên thuộc tính Java** và **tên field BSON**.
5. Phân tích lỗi dữ liệu thiếu trường, sai kiểu, đổi tên hoặc thay đổi cấu trúc object nhúng.
6. Kiểm thử round trip và dữ liệu legacy mà không chỉ dựa vào một document mẫu.

## 2. Luồng ánh xạ document lồng nhau

Spring Data MongoDB thường sử dụng **MappingMongoConverter** để chuyển giữa BSON document và object Java. Đối với một document gốc có object nhúng, framework đọc dữ liệu ở cấp gốc, sau đó tiếp tục tạo instance cho kiểu Java của các thuộc tính lồng nhau.

~~~mermaid
flowchart TD
    A["BSON customers document"] --> B["MappingMongoConverter"]
    B --> C["Customer"]
    C --> D["Thuộc tính address"]
    D --> E["Embedded BSON document"]
    E --> F["Chọn constructor của Address"]
    F --> G["Đọc giá trị theo mapping property"]
    G --> H["Gọi constructor Address"]
    H --> I["Customer chứa Address đã tạo"]
~~~

**Đọc object nhúng không giống truy vấn sang collection khác.** Một lớp Address là thành phần của Customer thường được lưu như subdocument ngay trong collection customers; không cần có collection address hoặc @Document riêng cho Address.

Spring Data cần hai nguồn thông tin:

- **Metadata của kiểu Java:** constructor nào sẽ được gọi, tên và kiểu của các tham số, các thuộc tính persistent và annotation mapping.
- **BSON document:** field nào đang tồn tại, giá trị, kiểu BSON và cấu trúc lồng nhau.

Sự lệch nhau giữa hai nguồn thông tin là nguyên nhân phổ biến của lỗi mapping.

## 3. Ví dụ đúng: constructor binding cho embedded Address

Lớp Customer là document gốc:

~~~java
package com.example.customers;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class Customer {

    @Id
    private final ObjectId id;

    private final String displayName;

    private final Address address;

    public Customer(ObjectId id, String displayName, Address address) {
        this.id = id;
        this.displayName = displayName;
        this.address = address;
    }

    public ObjectId getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Address getAddress() {
        return address;
    }
}
~~~

Lớp Address không cần @Document vì nó là object nhúng:

~~~java
package com.example.customers;

import org.springframework.data.mongodb.core.mapping.Field;

public class Address {

    private final String city;

    @Field("postal_code")
    private final String postalCode;

    public Address(String city, String postalCode) {
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

Các tham số **id**, **displayName**, **address**, **city** và **postalCode** cùng tên với các thuộc tính Java tương ứng. Đây là điều kiện quan trọng để Spring Data xác định giá trị constructor. Tên field BSON **postal_code** được ánh xạ đến thuộc tính Java **postalCode** nhờ @Field.

Khi mã được biên dịch với metadata tên tham số phù hợp, có thể đọc:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;

public class CustomerService {
    private final MongoTemplate mongoTemplate;

    public CustomerService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public String customerCity(String id) {
        ObjectId objectId = new ObjectId(id);
        Customer customer = mongoTemplate.findById(objectId, Customer.class);
        if (customer == null || customer.getAddress() == null) {
            return null;
        }
        return customer.getAddress().getCity();
    }
}
~~~

Với document ví dụ, hàm trên trả về **Đà Nẵng**. Khi đọc thành công, Spring Data đã chọn constructor Customer, sau đó tạo Address bằng các giá trị trong subdocument.

## 4. Tại sao tên tham số constructor lại quan trọng?

Trong Java source code, ta nhìn thấy:

~~~java
public Address(String city, String postalCode) {
    this.city = city;
    this.postalCode = postalCode;
}
~~~

Nhưng khi chương trình chạy, Spring Data làm việc với **class đã biên dịch**, không đọc lại file Java source. Nếu không giữ tên tham số, Java reflection có thể chỉ nhận được tên tổng quát như **arg0**, **arg1** thay vì **city**, **postalCode**.

Khi constructor được dùng để tạo object, Spring Data cần ghép tham số với **persistent property** của entity. Việc ghép này thường dựa vào tên tham số, hoặc metadata khác được framework hỗ trợ, chẳng hạn thông tin record. Vì vậy, thiếu tên tham số có thể dẫn đến lỗi không thể ánh xạ một tham số về thuộc tính nào.

### 4.1. Tên tham số là tên thuộc tính Java, không phải tên field BSON

Ví dụ:

~~~java
public class Address {
    @Field("postal_code")
    private final String postalCode;

    public Address(String postalCode) {
        this.postalCode = postalCode;
    }
}
~~~

**postalCode** là tên thuộc tính Java và tên tham số constructor; **postal_code** là tên field BSON. Spring Data dùng metadata @Field để ánh xạ hai phía.

Một lỗi dễ gặp là đổi tham số thành postal_code vì thấy MongoDB có field postal_code:

~~~java
// Ví dụ SAI về mặt constructor binding thông thường:
public Address(String postal_code) {
    this.postalCode = postal_code;
}
~~~

Tên tham số **postal_code** không khớp với property Java **postalCode**. Dù bên trong constructor gán đúng biến, bộ ánh xạ không suy luận theo thân hàm Java; nó phải tìm được property tương ứng từ metadata.

### 4.2. Tên tham số phải chính xác

Spring Data không tự suy rằng:

| Tên tham số | Tên thuộc tính Java | Có tự coi tương đương không? |
| --- | --- | --- |
| city | city | Có, khi metadata và kiểu phù hợp. |
| postalCode | postalCode | Có, khi metadata và kiểu phù hợp. |
| zipCode | postalCode | Không. |
| postal_code | postalCode | Không chỉ nhờ chuỗi field BSON. |
| name | displayName | Không. |
| customerAddress | address | Không. |

Đổi tên biến tham số mà không đổi thuộc tính Java tương ứng có thể phá cơ chế constructor binding khi đọc dữ liệu, kể cả khi mã vẫn biên dịch.

## 5. -parameters là gì?

**-parameters** là một tùy chọn của trình biên dịch Java **javac** yêu cầu ghi tên tham số phương thức và constructor vào bytecode để công cụ dùng reflection có thể đọc.

Ví dụ biên dịch thủ công:

~~~bash
javac -parameters Address.java
~~~

Một class Java bình thường không được biên dịch với -parameters có thể khiến reflection thấy **arg0**, **arg1**. Với -parameters, bytecode giữ metadata giúp nhìn thấy **city**, **postalCode**.

Tùy chọn này không đổi tên field BSON, không tạo schema cho MongoDB và không tự sửa các document có dữ liệu sai. Nó chỉ giúp các công cụ dựa vào metadata biết **tên tham số mà tác giả đã viết trong source**.

### 5.1. Cấu hình trong Maven

Một ví dụ cấu hình plugin compiler:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <parameters>true</parameters>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Nếu dự án kế thừa cấu hình compiler từ Spring Boot hoặc parent POM, -parameters có thể đã được thiết lập. Hãy **kiểm tra cấu hình build hiệu lực** thay vì luôn thêm plugin lần nữa.

### 5.2. Cấu hình trong Gradle

Với Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Đây là ví dụ hướng dẫn cấu hình, không yêu cầu thay đổi file build của module khi chỉ học bài này. Với Gradle Kotlin DSL, cú pháp cấu hình tương ứng khác Groovy DSL.

### 5.3. Cách xác minh metadata tham số

Java reflection có thể cho biết tên tham số có được biên dịch vào class hay không:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

Constructor<Address> constructor =
    Address.class.getDeclaredConstructor(String.class, String.class);

for (Parameter parameter : constructor.getParameters()) {
    System.out.println(
        parameter.getName() + ": " + parameter.isNamePresent()
    );
}
~~~

Với class bình thường được biên dịch bằng **-parameters**, kết quả có thể như sau:

~~~text
city: true
postalCode: true
~~~

Nếu metadata không có, kết quả thông thường là:

~~~text
arg0: false
arg1: false
~~~

Có thể kiểm tra bytecode bằng công cụ JDK:

~~~bash
javap -v -p com.example.customers.Address
~~~

Trong output, tìm thông tin **MethodParameters** của constructor. Nếu dự án có nhiều module build, kiểm tra đúng **class đang chạy**: việc một module đã bật -parameters không bảo đảm các dependency/module khác cũng được biên dịch như vậy.

### 5.4. -parameters không phải cách duy nhất

Một số loại class có nguồn metadata khác, chẳng hạn **Java record** lưu thông tin các component trong định nghĩa record. Framework có thể suy ra tên tham số của canonical constructor từ record metadata. Kotlin có metadata riêng khi dùng các thành phần Kotlin/Spring Data tương ứng.

Tuy nhiên, với **lớp Java thông thường có constructor tham số**, -parameters là lựa chọn rõ ràng và đáng tin cậy để phục vụ constructor binding. Không nên dựa vào debug symbols hoặc hành vi phụ thuộc compiler/phiên bản như một hợp đồng lâu dài.

## 6. Spring Data chọn constructor nào?

Một lớp có thể có no-args constructor, constructor đầy đủ tham số, các constructor phục vụ nghiệp vụ hoặc static factory. Spring Data cần quyết định **đường tạo instance** khi đọc BSON.

Các điểm chính của cơ chế chọn creator trong Spring Data:

1. Một constructor hoặc static factory được đánh dấu **@PersistenceCreator** có thể được dùng để chỉ định đường tạo instance.
2. Khi chỉ có một constructor phù hợp, Spring Data có thể chọn constructor đó.
3. Với **Java record**, canonical constructor thường là đường tạo đối tượng tự nhiên.
4. Khi có nhiều constructor và không khai báo rõ, đường chọn creator phụ thuộc các quy tắc của Spring Data và loại entity; đừng để framework phải phỏng đoán ý định.
5. Khi lớp có constructor không tham số được chọn, Spring Data có thể tạo instance rồi gán các persistent property thay vì phải bind mọi field vào constructor.

Chi tiết ưu tiên giữa nhiều constructor và static factory có thể thay đổi theo phiên bản Spring Data; cách thực tế nhất là **đánh dấu rõ constructor đọc dữ liệu** với @PersistenceCreator khi lớp có nhiều khả năng khởi tạo.

### 6.1. @PersistenceCreator

Ví dụ một embedded Address có nhiều constructor:

~~~java
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Field;

public class Address {
    private final String city;

    @Field("postal_code")
    private final String postalCode;

    @PersistenceCreator
    public Address(String city, String postalCode) {
        this.city = city;
        this.postalCode = postalCode;
    }

    public Address(String city) {
        this(city, null);
    }

    public String getCity() {
        return city;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

Annotation hướng dẫn Spring Data chọn constructor hai tham số để đọc dữ liệu, còn constructor một tham số phục vụ tạo object từ code ứng dụng. Khi gọi constructor đã chọn, Spring Data vẫn phải resolve tên city và postalCode thành các thuộc tính.

**@PersistenceCreator không thể tự sửa tên tham số sai.** Nếu annotation chỉ định constructor nhận một tham số name nhưng entity chỉ có property displayName, lỗi binding vẫn có thể xảy ra.

### 6.2. Phân biệt @PersistenceCreator và @Document

- **@Document** mô tả kiểu document gốc và collection.
- **@PersistenceCreator** mô tả constructor/factory cần dùng khi tạo object từ dữ liệu lưu trữ.
- **@Field** mô tả tên BSON field tương ứng với property Java.
- **@Id** mô tả property ánh xạ với BSON _id.

Embedded class Address thường **không cần @Document**, nhưng có thể cần @PersistenceCreator nếu có nhiều constructor hoặc cần chọn rõ đường mapping.

## 7. Lỗi tên constructor không khớp property

Xét lớp sau:

~~~java
public class CustomerName {
    private final String displayName;

    public CustomerName(String name) {
        this.displayName = name;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Dù constructor gán chính xác cho field displayName, tham số tên **name** không khớp tên property **displayName**. Khi Spring Data dùng constructor này để materialize CustomerName, nó không thể tự suy từ câu lệnh gán trong thân constructor rằng name thuộc về displayName.

Một bản sửa rõ ràng:

~~~java
public class CustomerName {
    private final String displayName;

    public CustomerName(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Khi vẫn cần tên tham số khác vì yêu cầu API hay thư viện, hãy cân nhắc thay đổi thiết kế constructor, sử dụng converter tùy chỉnh hoặc cách tạo instance khác phù hợp. Đừng kỳ vọng @Field của property tự làm tên tham số Java khác nhau trở thành đồng nghĩa.

## 8. Lỗi khác giữa Java property và BSON field

Mã Java có thể được thiết kế ổn định ngay cả khi BSON field dùng quy ước snake_case:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

public class Address {
    private final String city;

    @Field("postal_code")
    private final String postalCode;

    public Address(String city, String postalCode) {
        this.city = city;
        this.postalCode = postalCode;
    }
}
~~~

Document phù hợp:

~~~javascript
{
  address: {
    city: "Hà Nội",
    postal_code: "100000"
  }
}
~~~

Nếu MongoDB thực tế lưu **postalCode** nhưng Java chỉ ánh xạ **postal_code**, thuộc tính có thể trở thành null khi đọc hoặc gây lỗi ở constructor nếu không chấp nhận null:

~~~javascript
{
  address: {
    city: "Hà Nội",
    postalCode: "100000"
  }
}
~~~

Đây là **lỗi dữ liệu và hợp đồng field name**, khác với việc bytecode thiếu tên tham số. Bật -parameters không tự làm dữ liệu cũ đổi từ postalCode sang postal_code. Các lựa chọn xử lý gồm:

- Di chuyển dữ liệu cũ sang tên field BSON đã thống nhất.
- Dùng một lớp đọc tương thích nhiều schema và chuẩn hóa trước khi chuyển sang domain model.
- Dùng custom converter khi cấu trúc legacy phức tạp và nhiều nơi cần đọc thống nhất.
- Tránh cập nhật nguyên document nếu chưa hiểu các field legacy có nguy cơ bị bỏ mất.

## 9. Trường thiếu, null và giá trị mặc định

MongoDB phân biệt **field không tồn tại** và **field tồn tại với giá trị null**:

~~~javascript
// Thiếu postal_code.
{ address: { city: "Huế" } }

// Có postal_code nhưng giá trị null.
{ address: { city: "Huế", postal_code: null } }

// Đúng định dạng được chờ đợi.
{ address: { city: "Huế", postal_code: "530000" } }
~~~

Với constructor tham số kiểu **String**, việc không có giá trị có thể dẫn đến null được truyền vào constructor, tùy cơ chế mapping và dữ liệu. Nếu constructor yêu cầu không-null, nó cần biểu đạt rõ ràng:

~~~java
import java.util.Objects;

public Address(String city, String postalCode) {
    this.city = Objects.requireNonNull(city, "city is required");
    this.postalCode = Objects.requireNonNull(
        postalCode,
        "postalCode is required"
    );
}
~~~

Khi một document legacy thiếu postal_code, constructor có thể ném lỗi khi Spring Data đọc. Điều này không nhất thiết là lỗi -parameters; nó có thể là dữ liệu không đáp ứng bất biến mà Java đang áp đặt.

### 9.1. Primitive và kiểu boxed

Ví dụ một embedded LineItem:

~~~java
public record LineItem(String sku, int quantity) {}
~~~

Nếu quantity bị thiếu hoặc null trong BSON, Java primitive **int** không chứa null. Việc materialize record có thể thất bại do không có giá trị phù hợp cho tham số kiểu primitive. Dùng **Integer** có thể cho phép biểu diễn null, nhưng chỉ phù hợp nếu nghiệp vụ chấp nhận dữ liệu thiếu. Nếu quantity bắt buộc, nên xác nhận dữ liệu đầu vào và sử dụng validation/migration rõ ràng.

Không ngầm hiểu “missing có nghĩa bằng 0” khi 0 là giá trị nghiệp vụ có ý nghĩa khác với “chưa biết”. Việc gán default cần nằm trong hợp đồng dữ liệu.

### 9.2. Null cho toàn bộ object nhúng

Các trạng thái cũng khác nhau:

~~~javascript
{ displayName: "Lan" }                     // Không có address.
{ displayName: "Lan", address: null }      // Có address = null.
{ displayName: "Lan", address: {} }        // Address rỗng.
{ displayName: "Lan", address: { city: "Huế" } }
~~~

Trong Java, hai trường hợp đầu có thể cùng ánh xạ thành **address == null** nếu mô hình không lưu thông tin tồn tại field. Trường hợp **address: {}** yêu cầu tạo object Address từ subdocument rỗng; constructor với các tham số bắt buộc có thể thất bại. Nếu hệ thống cần phân biệt missing và null vì nghiệp vụ, hãy dùng mô hình dữ liệu/đường đọc đủ thông tin để giữ sự khác biệt.

## 10. Sai kiểu BSON và thay đổi schema

Constructor binding còn phụ thuộc **kiểu dữ liệu**. Hai document sau trông gần giống nhau nhưng không có cùng schema:

~~~javascript
// V1: address là chuỗi.
{
  displayName: "Lan",
  address: "Đà Nẵng"
}

// V2: address là embedded object.
{
  displayName: "Lan",
  address: { city: "Đà Nẵng", postal_code: "550000" }
}
~~~

Nếu Java khai báo **Address address**, document v1 chứa BSON String có thể không được converter mặc định chuyển thành Address theo ý định. Lỗi ở đây là **schema mismatch**, không phải thiếu metadata tên tham số.

Trong quá trình nâng cấp schema, cần quyết định:

1. Có bao nhiêu document đang dùng mỗi dạng?
2. Ứng dụng mới có phải đọc được cả hai dạng trong giai đoạn chuyển tiếp không?
3. Có thể chuyển String thành Address mà không mất thông tin không?
4. Lúc nào triển khai reader mới và lúc nào cho writer mới ghi cấu trúc mới?
5. Có cần thêm schemaVersion để xác định rõ format đang lưu không?

Chuyển đổi dữ liệu có thể thực hiện bằng migration theo lô hoặc một tầng adapter nhận dạng version. **Chỉ đổi kiểu field từ String sang Address trong code không tự chuyển toàn bộ BSON cũ.**

## 11. Constructor binding với Java record

Java record là lựa chọn thuận tiện khi biểu diễn immutable value object:

~~~java
public record AddressView(String city, String postalCode) {}
~~~

Record có **canonical constructor** và metadata component tương ứng. Trong các phiên bản Spring Data MongoDB hỗ trợ Java record, framework có thể dùng metadata record để ánh xạ các component mà không phải dựa hoàn toàn vào cách truy cập tên tham số của class thường.

Với tên BSON snake_case, có thể tách record miền khỏi hình dạng lưu trữ bằng converter, hoặc định nghĩa một lớp lưu trữ có @Field rõ ràng. Ví dụ record dùng tên BSON trùng component:

~~~java
public record AddressView(String city, String postalCode) {}
~~~

Document phù hợp:

~~~javascript
{
  address: {
    city: "Đà Nẵng",
    postalCode: "550000"
  }
}
~~~

Điều này **không có nghĩa record tự chuyển mọi tên field**: nếu MongoDB đang chứa postal_code, cần có mapping tương ứng hoặc migration. Cũng cần lưu ý canonical constructor được chọn phải có các component đúng kiểu; lỗi missing/null vẫn có thể xảy ra với record.

### 11.1. Constructor có tính toán hoặc validation

Một record có compact constructor:

~~~java
public record AddressView(String city, String postalCode) {
    public AddressView {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city must not be blank");
        }
    }
}
~~~

Nếu document cũ thiếu city, constructor sẽ ném lỗi. Việc này là **validation xảy ra khi đọc**, không chỉ khi ứng dụng tạo object mới. Cần quyết định chấp nhận hoặc chuyển đổi legacy schema trước khi áp dụng bất biến mạnh trên record.

## 12. Ánh xạ mảng các object nhúng

Một document có thể chứa danh sách địa chỉ:

~~~javascript
{
  displayName: "Lan",
  addresses: [
    { city: "Hà Nội", postal_code: "100000" },
    { city: "Đà Nẵng", postal_code: "550000" }
  ]
}
~~~

Lớp Java có thể khai báo:

~~~java
import java.util.List;

public class CustomerAddresses {
    private final String displayName;
    private final List<Address> addresses;

    public CustomerAddresses(
            String displayName,
            List<Address> addresses) {
        this.displayName = displayName;
        this.addresses = addresses;
    }

    public String getDisplayName() {
        return displayName;
    }

    public List<Address> getAddresses() {
        return addresses;
    }
}
~~~

Khi đọc, Spring Data phải tạo **mỗi phần tử Address** trong mảng. Nếu một phần tử dùng field sai tên, sai kiểu hoặc thiếu trường bắt buộc, việc đọc toàn bộ CustomerAddresses có thể thất bại.

Ví dụ một phần tử lỗi:

~~~javascript
{
  addresses: [
    { city: "Hà Nội", postal_code: "100000" },
    { city: { name: "Huế" }, postal_code: "530000" }
  ]
}
~~~

Thuộc tính city được chờ đợi là String nhưng một phần tử lại chứa object. Khi chẩn đoán, cần kiểm tra **vị trí phần tử trong mảng** cùng đường dẫn field, không chỉ document gốc.

Mảng hỗn hợp kiểu có thể được MongoDB lưu trữ, nhưng với **List<Address>** trong Java, nên thiết kế từng phần tử có cấu trúc nhất quán để mapping và kiểm thử đáng tin cậy.

## 13. Những lỗi mapping thường gặp và cách phân biệt

Lỗi có thể xuất hiện ở nhiều thời điểm: phát hiện creator, bind tham số, chuyển đổi giá trị, gọi constructor, gán field còn lại hoặc áp dụng callback. Tên exception cụ thể và nội dung message phụ thuộc phiên bản Spring Data, driver và nguyên nhân.

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Không thể ánh xạ tham số constructor thành property | Tên tham số không có hoặc sai tên | Kiểm tra -parameters, reflection isNamePresent, tên property Java. |
| Spring Data chọn constructor không mong đợi | Lớp có nhiều constructor hoặc factory | Xem quy tắc lựa chọn, @PersistenceCreator và metadata creator. |
| Tham số constructor nhận null dù BSON có dữ liệu | Tên field BSON không khớp @Field hoặc dữ liệu nằm ở đường dẫn khác | So sánh BSON thật và mapping property; kiểm tra nested path. |
| Constructor ném IllegalArgumentException/NullPointerException | Dữ liệu thiếu, null hoặc vi phạm bất biến nghiệp vụ | Kiểm tra giá trị field và stack trace của nguyên nhân gốc. |
| Không thể chuyển String thành Address | Schema cũ lưu chuỗi nhưng Java đang chờ object | Xác định các version và chuyển schema/adapter. |
| Một document đọc được, document khác lỗi | Collection có dữ liệu không đồng nhất | Thống kê kiểu BSON, kiểm tra bản ghi lỗi cụ thể. |
| Lỗi chỉ xảy ra với phần tử thứ hai trong mảng | Một embedded item có field sai kiểu | Kiểm tra từng phần tử của array. |
| Việc ghi thành công nhưng đọc lại thất bại | Mapping chiều ghi và chiều đọc không tương thích | Viết test round trip, kiểm tra constructor, @Field và converter. |
| Chạy local được nhưng deploy lỗi | Compiler/build module khác thiếu metadata hoặc dependency khác phiên bản | Kiểm tra bytecode thực tế, artifact đã deploy, -parameters. |

**Không nên xử lý mọi lỗi đọc object bằng cách thêm no-args constructor.** Cách đó có thể khiến framework chọn đường khởi tạo khác, che giấu dữ liệu sai hoặc làm giảm khả năng bảo vệ bất biến của immutable class. Trước hết cần xác định lỗi do metadata, tên field, kiểu BSON hay dữ liệu nghiệp vụ.

### 13.1. Phân loại lỗi theo tầng

Một quy trình suy luận hữu ích:

~~~mermaid
flowchart TD
    A["Không đọc được embedded object"] --> B{"Xác định đúng constructor?"}
    B -->|Không| C["Kiểm tra creator và @PersistenceCreator"]
    B -->|Có| D{"Tên tham số có và khớp property?"}
    D -->|Không| E["Kiểm tra -parameters, record, tên Java"]
    D -->|Có| F{"BSON field/kiểu dữ liệu khớp?"}
    F -->|Không| G["Kiểm tra @Field, schema, migration"]
    F -->|Có| H{"Constructor có ném lỗi?"}
    H -->|Có| I["Kiểm tra null, bất biến nghiệp vụ"]
    H -->|Không| J["Kiểm tra converter/callback và mapping còn lại"]
~~~

## 14. Chẩn đoán bằng dữ liệu MongoDB

Trước khi sửa class, cần xem **document thực tế**:

~~~javascript
db.customers.findOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { _id: 1, displayName: 1, address: 1 }
);
~~~

### 14.1. Kiểm tra kiểu BSON

Toán tử aggregation **$type** trả tên kiểu BSON của biểu thức:

~~~javascript
db.customers.aggregate([
  {
    $project: {
      displayName: 1,
      addressType: { $type: "$address" },
      cityType: { $type: "$address.city" },
      postalCodeType: { $type: "$address.postal_code" }
    }
  }
]);
~~~

Với document chuẩn, có thể thấy addressType là **object**, cityType và postalCodeType là **string**. Với document cũ hoặc dữ liệu lỗi, kết quả có thể là **missing**, **null**, **object** hay **string** ở vị trí không mong đợi.

Tìm document đang lưu address thành String:

~~~javascript
db.customers.find({
  address: { $type: "string" }
});
~~~

Tìm document có address là object nhưng không có postal_code:

~~~javascript
db.customers.find({
  address: { $type: "object" },
  "address.postal_code": { $exists: false }
});
~~~

Phân biệt **missing** và **null** theo yêu cầu nghiệp vụ. Điều kiện { field: null } trong MongoDB có thể khớp cả field null lẫn field thiếu; dùng $type hoặc $exists khi cần tách hai trường hợp.

### 14.2. Kiểm tra dữ liệu cũ không theo schema hiện hành

Nếu đã chuyển từ postalCode sang postal_code, thống kê các document còn dùng tên cũ:

~~~javascript
db.customers.countDocuments({
  "address.postalCode": { $exists: true }
});
~~~

Đó là cơ sở quyết định migration hoặc reader tương thích. **Không sửa annotation để khớp riêng một bản ghi** mà chưa xem mức độ phổ biến của từng schema.

## 15. Chẩn đoán bytecode và chọn đúng constructor

Khi stack trace nói không tìm được parameter hoặc property, hãy kiểm tra class thực sự được load bởi runtime:

1. Xem constructor nào có thể được Spring Data chọn và có annotation @PersistenceCreator hay không.
2. Với Java class thông thường, kiểm tra javac -parameters trên module sinh class đó.
3. Dùng reflection hoặc javap để xác nhận tên tham số trong bytecode.
4. So sánh từng tên tham số với property Java persistent, không chỉ với tên BSON field.
5. So sánh kiểu tham số với kiểu giá trị cần chuyển đổi.
6. Kiểm tra dữ liệu BSON thật, đặc biệt với các object/array nhúng hoặc record legacy.

Đoạn mã kiểm tra reflection cho Customer:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

for (Constructor<?> constructor : Customer.class.getDeclaredConstructors()) {
    System.out.println("Constructor: " + constructor);
    for (Parameter parameter : constructor.getParameters()) {
        System.out.println(
            "  " + parameter.getName()
            + ", present=" + parameter.isNamePresent()
            + ", type=" + parameter.getType().getName()
        );
    }
}
~~~

Mục đích là phát hiện các constructor có tham số mang tên arg0, arg1 hoặc bị đổi tên ngoài ý muốn. Đừng in giá trị dữ liệu nhạy cảm vào log khi chỉ cần chẩn đoán metadata và kiểu.

### 15.1. Vì sao chỉ sửa -parameters có thể chưa đủ?

Ngay cả khi reflection trả đúng city và postalCode, chương trình vẫn lỗi nếu:

- BSON lưu **postalCode** trong khi mapping yêu cầu **postal_code**.
- BSON lưu **address** là String, còn Java cần Address.
- Constructor từ chối null ở field bị thiếu.
- Một converter được đăng ký làm thay đổi logic đọc.
- Lớp có nhiều constructor và Spring Data chọn sai creator.
- Ứng dụng đang chạy một artifact cũ chưa chứa bản compile mới.

Cần kiểm tra **đầy đủ chuỗi từ BSON tới object Java**, thay vì chỉ dựa vào một flag build.

## 16. Kiểm thử tích hợp cho embedded objects

Unit test khởi tạo Address trực tiếp bằng new Address(...) chỉ chứng minh constructor Java hoạt động. Nó **không kiểm tra** việc Spring Data đọc tên field BSON, xác định parameter name hay gọi đúng creator.

Kiểm thử tốt cần:

1. Ghi document thực sự vào collection test.
2. Đọc lại bằng Spring Data MongoTemplate hoặc repository.
3. Kiểm tra object nhúng và các property của nó.
4. Có thêm trường hợp thiếu field, sai tên, sai kiểu hoặc dữ liệu cũ.
5. Chỉ chạy với database dành riêng cho test và dọn dữ liệu sau kiểm thử.

Ví dụ JUnit 5 với MongoTemplate:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class CustomerMappingTest {

    @Autowired
    private MongoTemplate mongoTemplate;

    @Test
    void readsEmbeddedAddressUsingConstructorParameters() {
        ObjectId id = new ObjectId();

        Document raw = new Document("_id", id)
            .append("displayName", "Lan")
            .append("address", new Document("city", "Đà Nẵng")
                .append("postal_code", "550000"));

        mongoTemplate.getCollection("customers").insertOne(raw);
        try {
            Customer loaded = mongoTemplate.findById(
                id, Customer.class
            );
            assertThat(loaded).isNotNull();
            assertThat(loaded.getAddress()).isNotNull();
            assertThat(loaded.getAddress().getCity())
                .isEqualTo("Đà Nẵng");
            assertThat(loaded.getAddress().getPostalCode())
                .isEqualTo("550000");
        } finally {
            mongoTemplate.getCollection("customers")
                .deleteOne(new Document("_id", id));
        }
    }
}
~~~

Kiểm thử này cố ý **ghi BSON thô bằng driver** rồi đọc bằng mapping Spring Data. Nhờ đó, nó kiểm tra đúng chiều đọc từ field **postal_code** sang property **postalCode**, thay vì để cùng một converter ghi và đọc rồi che giấu lỗi khi dữ liệu legacy có hình dạng khác.

### 16.1. Test cả dữ liệu sai để xác định hợp đồng

Nên bổ sung các fixture sau:

| Fixture BSON | Kỳ vọng do nhóm quyết định |
| --- | --- |
| address hợp lệ, postal_code là String | Đọc được, đúng giá trị. |
| address thiếu hẳn | Cho phép null hoặc báo lỗi theo business rule. |
| address = null | Có xử lý rõ, không coi như object đầy đủ. |
| address = {} | Không làm mất bất biến constructor. |
| address.postalCode thay cho postal_code | Có migration/adapter hoặc phát hiện dữ liệu lỗi. |
| address.city là Object thay vì String | Báo lỗi chuyển đổi hoặc chính sách xử lý đặc biệt. |
| addresses chứa một phần tử sai kiểu | Phát hiện và chỉ ra document/phần tử lỗi. |

Nếu cần **bảo toàn tính toàn vẹn dữ liệu**, có thể dùng collection validation với $jsonSchema để kiểm tra kiểu BSON của embedded fields. Validator không tự chuyển dữ liệu cũ; phải kết hợp thống kê và migration.

## 17. Tác động đến truy vấn, index và hiệu năng

Tên field lưu thực tế còn quyết định cách MongoDB tìm và đánh index:

~~~javascript
db.customers.createIndex({ "address.postal_code": 1 });
db.customers.find({ "address.postal_code": "550000" });
~~~

Trong ứng dụng Spring Data MongoDB, khi viết **Query** có thông tin entity class, mapping có thể chuyển đường dẫn property Java sang tên field BSON theo @Field. Nhưng khi viết truy vấn bằng **MongoDB Java Driver trực tiếp**, bạn phải dùng tên field đang lưu thật sự, ví dụ **address.postal_code**.

Nếu dữ liệu lẫn **address.postal_code** và **address.postalCode**, index trên một đường dẫn không tự bao phủ đường dẫn còn lại. Các truy vấn và aggregation có thể bỏ sót dữ liệu. Trước khi kết luận việc đọc chậm do constructor, hãy kiểm tra **query plan, index, số document scan, BSON schema và các điều kiện lọc**.

Constructor binding chủ yếu xảy ra khi chuyển kết quả truy vấn thành object. Lỗi dữ liệu sai kiểu có thể xuất hiện ở cuối hành trình truy vấn, sau khi MongoDB đã tìm ra document; không nên nhầm nó với lỗi “query không trả kết quả”.

Trong **ReactiveMongoTemplate** và reactive repository, cơ chế ánh xạ embedded object vẫn phải xử lý cùng các thuộc tính và constructor. Khác biệt chủ yếu là lỗi được phát qua reactive publisher khi đọc và mapping xảy ra, không có nghĩa lỗi data mapping sẽ biến mất.

## 18. Kỹ thuật thiết kế giúp tránh lỗi

Khi thiết kế embedded object mới hoặc refactor class cũ:

- **Giữ tên tham số constructor khớp property Java**. Dùng @Field cho khác biệt giữa Java và BSON; không đổi tên tham số theo tên BSON.
- **Biên dịch với -parameters** đối với Java class cần constructor binding; xác minh metadata ở artifact chạy thật.
- **Chọn creator rõ ràng** nếu lớp có nhiều constructor hoặc factory.
- **Ưu tiên bất biến nghiệp vụ có chủ đích**. Nếu dữ liệu cũ có thể thiếu field, xác định cách chuyển đổi trước khi đưa validate chặt vào constructor.
- **Thiết kế migration cho schema cũ**. Nếu field được đổi tên hoặc đổi kiểu, nâng cấp đường đọc và dữ liệu cùng kế hoạch.
- **Kiểm thử đọc BSON thực**. Dữ liệu fixture phải có cả case đúng và case lỗi.
- **Giữ log hữu ích**. Ghi định danh bản ghi, đường dẫn field, kiểu BSON và nguyên nhân; hạn chế ghi giá trị nhạy cảm.
- **Không phụ thuộc vào cứu chữa bằng no-args constructor** khi lỗi nằm ở schema hoặc tên field.

### 18.1. Khi nào nên dùng custom converter?

Một converter tùy chỉnh phù hợp khi dữ liệu lịch sử có **nhiều cấu trúc không thể ánh xạ trực tiếp**. Ví dụ address trước đây là String, sau là document, sau nữa là danh sách nhiều địa chỉ. Converter có thể chuẩn hóa từng dạng trước khi tạo domain model.

Nhưng converter cũng có chi phí:

1. Cần kiểm thử kỹ các trường hợp dữ liệu legacy.
2. Phải thống nhất giữa đọc và ghi để không vô tình làm mất field.
3. Có thể che giấu sai schema nếu tự động chuyển mọi giá trị không hợp lệ thành mặc định.
4. Cần xem xét ảnh hưởng tới query mapping và projection nếu dùng các cơ chế đặc thù.

Với lớp có mapping thông thường, **đặt đúng property/parameter name và @Field** thường đơn giản hơn custom converter.

## 19. Bài tập thực hành

### Bài tập 1: thiếu -parameters

Cho lớp Java thường:

~~~java
public class Address {
    private final String city;
    private final String postalCode;

    public Address(String city, String postalCode) {
        this.city = city;
        this.postalCode = postalCode;
    }
}
~~~

**Câu hỏi:** Java reflection có thể in tên arg0, arg1. Điều gì cần kiểm tra trước khi sửa dữ liệu MongoDB?

**Gợi ý đáp án:** kiểm tra class đã được biên dịch với javac -parameters chưa; dùng reflection isNamePresent hoặc javap MethodParameters trên artifact thực tế; xác nhận Spring Data chọn đúng constructor. Nếu thiếu metadata, cấu hình compiler phù hợp và build lại class liên quan.

### Bài tập 2: tên tham số không khớp

~~~java
public class Location {
    private final String countryCode;

    public Location(String code) {
        this.countryCode = code;
    }
}
~~~

**Câu hỏi:** tại sao bật -parameters chưa chắc giải quyết lỗi?

**Gợi ý đáp án:** -parameters chỉ giữ tên **code**, không đổi nó thành **countryCode**. Constructor binding cần tìm persistent property phù hợp. Đổi tên tham số thành countryCode hoặc dùng chiến lược mapping rõ ràng khác.

### Bài tập 3: Java camelCase và BSON snake_case

MongoDB lưu:

~~~javascript
{ address: { city: "Huế", postal_code: "530000" } }
~~~

Trong Java, property là postalCode. Hãy chọn tên tham số và annotation phù hợp.

**Gợi ý đáp án:** khai báo property postalCode có **@Field("postal_code")**, constructor nhận tham số **postalCode**. Tên tham số không cần đổi thành postal_code.

### Bài tập 4: dữ liệu legacy có kiểu khác

Collection có 40% document với address String, 60% với address Object. Ứng dụng mới chỉ dùng lớp Address. Bạn sẽ làm gì?

**Gợi ý đáp án:** thống kê dữ liệu, thiết kế reader hỗ trợ hai dạng hoặc migration có kiểm soát, chạy kiểm thử với fixture của cả hai nhóm, sau đó mới ngừng hỗ trợ dạng cũ. Không cho rằng đổi Java field type tự đổi BSON.

### Bài tập 5: object nhúng bị null

Constructor Address sử dụng Objects.requireNonNull(city), nhưng một document có address = {}. Khi đọc, lỗi có thể xuất hiện ở đâu?

**Gợi ý đáp án:** tại bước tạo Address bằng constructor; city không có giá trị và validation ném lỗi. Xem dữ liệu thực tế và chính sách bắt buộc của city, không chỉ thêm -parameters.

### Bài tập 6: kiểm thử hai chiều

Viết test xác nhận Address có city và postalCode được ghi thành field city và postal_code, sau đó đọc lại. Vì sao cần thêm một test đọc document BSON được tạo thủ công?

**Gợi ý đáp án:** test round trip kiểm chứng cả hai chiều trong cấu hình hiện tại; test với BSON thô đảm bảo dữ liệu lịch sử và contract ngoài ứng dụng cũng tương thích. Nếu chỉ dùng cùng converter để ghi và đọc, hai phía có thể cùng dùng tên sai mà test vẫn vượt qua.

## 20. Ghi nhớ khi làm việc với constructor và embedded objects

1. **Constructor binding nối tên tham số với persistent property Java**, sau đó Spring Data dùng metadata mapping để đọc field BSON tương ứng.
2. **-parameters giữ tên tham số ở bytecode** cho Java class thông thường; nó không tạo hoặc sửa field MongoDB.
3. **@Field thay đổi tên BSON field**, còn tên tham số constructor thông thường phải khớp tên property Java.
4. **@PersistenceCreator giúp chọn rõ constructor** trong lớp có nhiều cách khởi tạo; annotation không tự sửa sai tên tham số.
5. **Java record hỗ trợ immutable mapping thông qua component/canonical constructor**, nhưng không miễn trừ việc kiểm tra schema BSON và null.
6. **Sai tên field, field thiếu, null và sai kiểu là các vấn đề khác nhau**. Đừng xử lý tất cả bằng một cấu hình compiler.
7. **Embedded object và mảng embedded cũng đi qua quy trình mapping**, nên một phần tử lỗi có thể làm thất bại việc đọc toàn bộ document.
8. **Kiểm thử với MongoDB thật và dữ liệu legacy** giúp phát hiện lỗi mà unit test constructor hoặc dữ liệu mới tự sinh không thể thấy.

Nắm vững tên tham số constructor, tùy chọn **-parameters** và cách đối chiếu dữ liệu BSON giúp ứng dụng **SPRING_DATA_MONGODB** đọc, ghi và bảo trì document nhúng an toàn hơn khi dùng MongoTemplate, repository và các luồng truy cập dữ liệu nâng cao.
