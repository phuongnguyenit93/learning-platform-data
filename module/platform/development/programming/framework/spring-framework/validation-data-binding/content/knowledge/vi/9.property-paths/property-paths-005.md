# Đường dẫn lồng qua đối tượng đang null trong Spring Data Binding

Một đường dẫn thuộc tính lồng nhau như **student.address.city** mô tả cách đi từ đối tượng gốc đến thuộc tính cần gán: lấy **student**, lấy **address** của student, rồi gán **city**. Điều gì xảy ra nếu **student == null** hoặc **student.getAddress() == null** tại thời điểm bind?

Với **property binding** của Spring Framework, kết quả phụ thuộc chủ yếu vào **autoGrowNestedPaths**. **DataBinder** tiêu chuẩn mặc định bật cơ chế này: nếu có thể, Spring tạo đối tượng trung gian đang **null**, gắn nó trở lại object graph rồi đi tiếp. Khi tắt cơ chế hoặc không thể tạo object, đường dẫn không thể được duyệt bình thường; tùy API và chính sách bỏ qua field, ứng dụng sẽ gặp lỗi hoặc bỏ qua dữ liệu.

Điểm quan trọng: **đối tượng con được tạo tự động để gán thuộc tính không đồng nghĩa dữ liệu đã được validate hoặc nghiệp vụ đã chấp nhận**. Hơn nữa, cơ chế này áp dụng cho **property/field binding**; không được mặc nhiên đồng nhất với việc Jackson đọc JSON hoặc **constructor binding**.

## 1. Đọc đúng ý nghĩa của một nested property path

Xét ba lớp JavaBean:

~~~java
public class EnrollmentForm {
    private Student student;      // ban đầu null
    public Student getStudent() { return student; }
    public void setStudent(Student student) { this.student = student; }
}

public class Student {
    private Address address;      // ban đầu null
    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }
}

public class Address {
    private String city;          // ban đầu null
    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
}
~~~

Đây là **mã minh họa cấu trúc**: khi đặt trong tệp Java thật, cần tách các public top-level class thành các tệp tương ứng hoặc dùng nested static classes. Phần 4 cung cấp một chương trình độc lập đúng quy tắc biên dịch.

Đường dẫn **student.address.city** có các mắt xích:

~~~text
EnrollmentForm (đối tượng gốc tồn tại)
      |
      +-- student = null
                |
                +-- address = ?      (chưa thể đọc khi student null)
                        |
                        +-- city = ? (chưa thể gán)
~~~

Không thể gọi **form.getStudent().getAddress().setCity("Hà Nội")** bằng Java thông thường khi **getStudent()** trả **null**: Java ném **NullPointerException**. Spring **BeanWrapper** không thực hiện cách gọi setter một cách mù quáng; nó kiểm tra đường dẫn và, nếu được cấu hình, có thể tự tạo các đối tượng trung gian.

Ví dụ khi nhận **student.address.city=Hà Nội**:

1. Spring tìm property **student** trên **EnrollmentForm**.
2. Nếu **student == null** và tự mở rộng đường dẫn đang bật, Spring tạo một **Student** mặc định rồi gán thông qua property tương ứng.
3. Spring tìm **address** trên **Student**; nếu **null**, tạo **Address** mặc định rồi gán lại.
4. Spring chuyển kiểu giá trị đầu vào nếu cần, sau đó gọi setter của **city**.
5. Đối tượng gốc bây giờ có **student != null**, **address != null**, **city = "Hà Nội"**.

Cơ chế được gọi là **auto-grow nested paths**. Việc tự tạo chỉ xảy ra khi quá trình duyệt cần vượt qua một vị trí **null**; nếu không có dữ liệu nào yêu cầu đi tới **student.address.city**, không có lý do để kết luận Spring sẽ chủ động tạo toàn bộ cây đối tượng.

**Phân biệt null ở giữa và null ở cuối:** với **student.address.city**, **student** và **address** là các nút trung gian phải tồn tại để đi tiếp; **city** là giá trị đích và hoàn toàn có thể được gán **null** khi hợp đồng property cho phép. Một leaf null tự nó không phải lỗi “không thể đi qua nested path”.

## 2. Các API và giá trị mặc định phải nhớ

| API hoặc cấu hình | Ý nghĩa | Mặc định cần lưu ý |
| --- | --- | --- |
| **DataBinder.setAutoGrowNestedPaths(boolean)** | Cho phép hoặc ngăn việc tự tạo các object trung gian khi bind theo property path | **true** trên DataBinder chuẩn |
| **DataBinder.isAutoGrowNestedPaths()** | Đọc trạng thái bật/tắt | **true** trên binder mới tạo |
| **BeanWrapperImpl.setAutoGrowNestedPaths(boolean)** | Tùy chọn tương tự trên accessor cấp thấp | **false** với BeanWrapperImpl tạo trực tiếp |
| **DataBinder.setAutoGrowCollectionLimit(int)** | Giới hạn số phần tử tự thêm cho array/collection | **256** trên DataBinder chuẩn |
| **DataBinder.setIgnoreInvalidFields(boolean)** | Chọn bỏ qua input field tương ứng với đường dẫn có property nhưng hiện không truy cập được, ví dụ nút trung gian null | **false** |
| **DataBinder.setIgnoreUnknownFields(boolean)** | Chọn bỏ qua tên field không tồn tại trên kiểu đích | **true** |
| **DataBinder.setAllowedFields(String...)** | Giới hạn property được phép bind | Chưa giới hạn nếu không cấu hình |

**Hai mặc định dễ bị nhầm:** **DataBinder** có **autoGrowNestedPaths = true**, trong khi **BeanWrapperImpl** mới tạo trực tiếp mặc định **false**. Vì vậy hai đoạn code thoạt nhìn giống nhau có thể xử lý null khác nhau:

~~~java
DataBinder binder = new DataBinder(form, "enrollmentForm");
// binder.isAutoGrowNestedPaths() -> true

BeanWrapperImpl wrapper = new BeanWrapperImpl(form);
// wrapper.isAutoGrowNestedPaths() -> false
~~~

Các biến **form**, kiểu import **DataBinder** và **BeanWrapperImpl** ở đoạn trên do ứng dụng cung cấp. Khi dùng **BeanWrapper** tự tạo, có thể bật rõ ràng bằng **wrapper.setAutoGrowNestedPaths(true)** trước khi truy cập đường dẫn.

**Thời điểm cấu hình cũng quan trọng.** Với **DataBinder**, hãy gọi **setAutoGrowNestedPaths(false)** hoặc **setAutoGrowCollectionLimit(...)** **trước** khi binder khởi tạo accessor/BindingResult. Chẳng hạn gọi **binder.getBindingResult()** rồi mới cố đổi cấu hình tự mở rộng có thể dẫn đến **IllegalStateException** vì binder đã được khởi tạo. Nên cấu hình ngay sau **new DataBinder(...)**, trước **bind(...)** hoặc các thao tác buộc binder khởi tạo.

## 3. Điều kiện để auto-grow hoạt động

Bật cờ **true** không biến Spring thành một dependency-injection container cho bất kỳ nested object nào. Để auto-grow một giá trị **null**, Spring cần biết kiểu thuộc tính, tạo được một giá trị mặc định thích hợp và gắn nó lại vào object graph.

Đối với một JavaBean thông thường, yêu cầu thực tế gồm:

- Đối tượng gốc đã tồn tại cho property binding, ví dụ **new EnrollmentForm()**.
- Các property trung gian được xác định qua getter/setter phù hợp trong bean-property access (hoặc qua field khi dùng direct-field access có hỗ trợ).
- Kiểu trung gian đủ cụ thể để tạo instance; thường là một class có constructor không tham số mà Spring có thể sử dụng. Interface thuần, abstract class hoặc kiểu chỉ có constructor bắt buộc tham số thường không thể tự tạo theo cách mặc định.
- Sau khi tạo, accessor phải có cách gắn giá trị mới vào thuộc tính cha; getter thiếu, setter không khả dụng, kiểu không khớp hoặc code trong getter/setter ném exception có thể làm quá trình thất bại.
- Nếu đường dẫn đi qua **List**, array hoặc **Map**, Spring còn cần thông tin kiểu phần tử/key/value và cấu trúc có thể tự mở rộng. Giới hạn collection áp dụng riêng.

Không nên viết “Spring sẽ tự tạo **mọi** object null”. Cụm đúng hơn là: **Spring thử khởi tạo giá trị mặc định tại vị trí null nếu cơ chế auto-grow đang bật và kiểu đích có thể được tạo/gắn**.

Một trường hợp thường gặp không chạy:

~~~java
public class Form {
    private Location location;
    public Location getLocation() { return location; }
    public void setLocation(Location location) { this.location = location; }
}

public interface Location {
    String getCity();
    void setCity(String city);
}
~~~

Đây chỉ là ví dụ giải thích. Nếu **location == null** và khai báo kiểu **Location** là interface, Spring không thể tự **new Location()** bằng constructor mặc định. Muốn bind **location.city**, hãy cung cấp một instance concrete từ trước, thiết kế DTO khác, hoặc dùng cơ chế khởi tạo/constructor binding phù hợp. **Một Converter cho String không tự giải quyết việc không thể khởi tạo object trung gian kiểu interface.**

Cũng cần cẩn thận với **record** hoặc immutable object có các field **final** và không có setter: mô hình đó phù hợp hơn với **constructor binding**; không nên giả định auto-grow property binding có thể thay đổi chúng giống JavaBean mutable.

## 4. Ví dụ hoàn chỉnh: cùng đường dẫn, ba cách xử lý

Chương trình sau dùng **Java 17+** và **Spring Framework 6.2.10**, không cần Spring Boot hay web server. Nó minh họa:

1. **DataBinder** mặc định tự tạo **Student** và **Address** vốn đang null.
2. **BeanWrapperImpl** tạo trực tiếp không bật auto-grow báo **NullValueInNestedPathException** khi đi qua **student == null**.
3. **DataBinder** tắt auto-grow vẫn bind được nếu ứng dụng **khởi tạo sẵn** toàn bộ object trung gian.

Tạo hai tệp:

~~~text
nested-null-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── NestedNullDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>nested-null-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/NestedNullDemo.java**:

~~~java
package demo;

import java.util.Map;

import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NullValueInNestedPathException;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

public final class NestedNullDemo {

    public static void main(String[] args) {
        // Case 1: Hai nút trung gian chưa được khởi tạo.
        EnrollmentForm form = new EnrollmentForm();
        System.out.println("beforeStudentNull=" + (form.getStudent() == null));

        DataBinder binder = new DataBinder(form, "enrollmentForm");
        System.out.println("binderAutoGrow=" + binder.isAutoGrowNestedPaths());

        // Chỉ cho phép hai field dùng trong tình huống này.
        binder.setAllowedFields(
                "student.address.city",
                "student.address.zipCode");

        binder.bind(new MutablePropertyValues(Map.of(
                "student.address.city", "Hà Nội",
                "student.address.zipCode", "100000"
        )));

        BindingResult result = binder.getBindingResult();

        System.out.println("bindErrors=" + result.hasErrors());
        System.out.println("studentCreated=" + (form.getStudent() != null));
        System.out.println("addressCreated="
                + (form.getStudent().getAddress() != null));
        System.out.println("city="
                + form.getStudent().getAddress().getCity());
        System.out.println("zipCode="
                + form.getStudent().getAddress().getZipCode());

        // Case 2: BeanWrapperImpl riêng có mặc định KHÔNG auto-grow.
        BeanWrapperImpl plain = new BeanWrapperImpl(new EnrollmentForm());
        System.out.println("plainWrapperAutoGrow="
                + plain.isAutoGrowNestedPaths());
        try {
            plain.setPropertyValue("student.address.city", "Huế");
            System.out.println("unexpectedSuccess");
        } catch (NullValueInNestedPathException exception) {
            System.out.println("plainFailure="
                    + exception.getClass().getSimpleName());
        }

        // Case 3: Tắt auto-grow, nhưng chủ động khởi tạo các nút cha.
        EnrollmentForm prebuilt = new EnrollmentForm();
        Student student = new Student();
        student.setAddress(new Address());
        prebuilt.setStudent(student);

        DataBinder manual = new DataBinder(prebuilt, "enrollmentForm");
        manual.setAutoGrowNestedPaths(false);
        manual.setAllowedFields("student.address.city");
        manual.bind(new MutablePropertyValues(Map.of(
                "student.address.city", "Đà Nẵng"
        )));

        System.out.println("manualAutoGrow=" + manual.isAutoGrowNestedPaths());
        System.out.println("manualErrors="
                + manual.getBindingResult().hasErrors());
        System.out.println("manualCity="
                + prebuilt.getStudent().getAddress().getCity());
    }

    public static class EnrollmentForm {
        private Student student;

        public EnrollmentForm() {
        }

        public Student getStudent() {
            return student;
        }

        public void setStudent(Student student) {
            this.student = student;
        }
    }

    public static class Student {
        private Address address;

        public Student() {
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static class Address {
        private String city;
        private String zipCode;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public String getZipCode() {
            return zipCode;
        }

        public void setZipCode(String zipCode) {
            this.zipCode = zipCode;
        }
    }
}
~~~

Trong thư mục **nested-null-demo**, dùng JDK 17 hoặc mới hơn và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.NestedNullDemo
~~~

**Các dòng do chương trình in ra**, không tính thông báo của công cụ build:

~~~text
beforeStudentNull=true
binderAutoGrow=true
bindErrors=false
studentCreated=true
addressCreated=true
city=Hà Nội
zipCode=100000
plainWrapperAutoGrow=false
plainFailure=NullValueInNestedPathException
manualAutoGrow=false
manualErrors=false
manualCity=Đà Nẵng
~~~

Giải thích từng case:

- **Case 1:** không có **new Student()** hoặc **new Address()** trong code của ứng dụng trước lúc bind. Chính quá trình duyệt **student.address.city** đã khiến DataBinder tạo rồi gắn chúng, bởi **autoGrowNestedPaths** mặc định bật. Hai field String được gán thành công, nên **BindingResult.hasErrors()** trả **false**.
- **Case 2:** dùng một **BeanWrapperImpl** mới, không cấu hình auto-grow. Với cùng đường dẫn, tại nút **student == null** không thể đi tiếp; ví dụ bắt đúng **NullValueInNestedPathException**. Đây là lỗi đường dẫn null, không phải **NullPointerException** được ném từ đoạn gọi setter trong code người học.
- **Case 3:** **autoGrowNestedPaths(false)** chỉ ngăn Spring tự tạo nút null; nó không cấm truy cập nested property vốn đã tồn tại. Vì **prebuilt.student.address** được khởi tạo trước, binder vẫn gán **city** và không có lỗi.

**Case 2 minh họa hành vi của BeanWrapperImpl trực tiếp, không phải khẳng định mọi lỗi của DataBinder đều được đóng gói thành FieldError.** Với đường dẫn không truy cập được, API cấp thấp có thể ném **NullValueInNestedPathException**; trong pipeline bind, cần phân biệt ngoại lệ truy cập property và lỗi chuyển kiểu được tổng hợp trong **BindingResult**.

## 5. Khi tắt auto-grow trên DataBinder

Có hai lựa chọn thiết kế, tùy nhu cầu của form:

**Tự mở rộng đường dẫn (mặc định):**

~~~java
EnrollmentForm target = new EnrollmentForm();
DataBinder binder = new DataBinder(target, "enrollmentForm");
// autoGrowNestedPaths mặc định true
binder.bind(new MutablePropertyValues(
        Map.of("student.address.city", "Hà Nội")));
~~~

**Không tự mở rộng, chủ động chuẩn bị object graph:**

~~~java
EnrollmentForm target = new EnrollmentForm();
Student student = new Student();
student.setAddress(new Address());
target.setStudent(student);

DataBinder binder = new DataBinder(target, "enrollmentForm");
binder.setAutoGrowNestedPaths(false);
binder.bind(new MutablePropertyValues(
        Map.of("student.address.city", "Hà Nội")));
~~~

Đây là **hai đoạn minh họa** dùng các class và import như ở phần 4. Đặt **setAutoGrowNestedPaths(false)** trước khi binder khởi tạo.

Nếu tắt auto-grow trong khi **student == null** mà vẫn gửi **student.address.city**, đường dẫn không truy cập được. Mặc định **setIgnoreInvalidFields(false)**; không nên dựa vào giả định **bind(...)** sẽ tự lặng lẽ bỏ field hoặc luôn trả một **BindingResult** có lỗi kiểu dữ liệu. Với **BeanWrapper** cấp thấp, trường hợp này rõ ràng dẫn tới **NullValueInNestedPathException**.

Cũng có tùy chọn:

~~~java
binder.setIgnoreInvalidFields(true);
~~~

Nó yêu cầu binder **bỏ qua những field có property path không truy cập được**, trong đó có trường hợp một nút trung gian đang null. Đây **không phải** cách tự tạo object, cũng không phải cách sửa lỗi dữ liệu. Nếu ứng dụng lặng lẽ bỏ qua **student.address.city**, giá trị người dùng gửi có thể không được ghi vào target. Do đó không bật tùy chọn này chỉ để làm cho request “hết lỗi”; phải xác minh yêu cầu nghiệp vụ có thật sự cho phép bỏ qua field.

### Invalid field khác unknown field

Hai trường hợp dễ bị trộn lẫn:

| Trường hợp | Ví dụ | Vấn đề | Cấu hình có liên quan |
| --- | --- | --- | --- |
| **Đường dẫn tồn tại nhưng không đi qua được** | **student.address.city**, trong khi **student == null** và không auto-grow | Nút trung gian không truy cập được | **autoGrowNestedPaths**, **ignoreInvalidFields** |
| **Tên thuộc tính không tồn tại** | **student.address.planetName** khi Address không có property này | Không tìm thấy field/property đích | **ignoreUnknownFields** |
| **Giá trị không chuyển được sang kiểu đích** | **student.age = "abc"**, nhưng age là **Integer** | Type conversion thất bại | **ConversionService**, binding error |
| **Field bị chặn bởi allowedFields** | Gửi **student.role** nhưng binder chỉ cho **student.address.city** | Chính sách cho phép bind | **setAllowedFields(...)**, **getSuppressedFields()** |

Mặc định **ignoreUnknownFields = true** không có nghĩa **ignoreInvalidFields = true**. Và một trường bị chặn bởi **allowedFields** không phải lỗi “đối tượng trung gian null”. Khi chẩn đoán phải nhìn đúng nguyên nhân.

## 6. Null ở các mức khác nhau và tính chất không nguyên tử của binding

Một request có thể gửi nhiều đường dẫn cùng lúc:

~~~text
student.address.city=Hà Nội
student.address.zipCode=100000
student.fullName=Lan
~~~

Nếu hệ thống bind lần lượt các property, việc đi qua **student** sẽ tạo instance một lần rồi tái sử dụng. Nếu **address** đã được tạo vì **city**, **zipCode** được gán vào cùng object đó. Kết quả cuối cùng phải được kiểm tra trên **cây object**, không chỉ xem một setter có được gọi hay không.

Nhưng **DataBinder.bind(...) không phải một database transaction**. Ví dụ binder gán thành công **student.address.city**, rồi thất bại khi chuyển **student.age = "abc"** sang **Integer**. Những property đã gán có thể vẫn nằm trong object, còn **BindingResult** báo lỗi ở field thất bại. Không giả định khi có một lỗi thì Spring tự hoàn tác mọi thay đổi trước đó.

Luồng xử lý an toàn là:

1. Bind vào một **request DTO** riêng với miền thuộc tính được cho phép.
2. Đọc **BindingResult** và dừng trước khi gọi service nếu còn lỗi binding.
3. Kích hoạt Bean Validation hoặc Spring Validator phù hợp để kiểm tra giá trị bắt buộc, độ dài, quy tắc chéo field.
4. Chỉ chuyển đổi dữ liệu hợp lệ sang domain command/entity và thực hiện nghiệp vụ theo transaction thích hợp.

**Nếu form không gửi bất kỳ trường nào thuộc student**, auto-grow không bảo đảm student được tạo. Ngược lại, **nếu nó tự tạo Student/Address rỗng từ một field nào đó**, sự tồn tại của object không chứng minh các trường bắt buộc bên trong đã có giá trị. Điều này đặc biệt quan trọng với **@Valid**, **@NotNull** và **@NotBlank**.

## 7. Collection, array, map: null và index lồng nhau

Spring hỗ trợ đường dẫn chứa index/key như:

~~~text
students[0].address.city
students[2].address.city
settings[timezone].value
~~~

Ở đó có thể gặp nhiều loại “trống” khác nhau: collection là **null**; collection đã tồn tại nhưng index chưa có phần tử; phần tử tại index là **null**; hoặc **address** của phần tử là **null**.

Khi auto-grow bật, Spring có thể tạo collection/array hoặc phần tử trung gian theo thông tin kiểu mà nó xác định được. Với một **List<Student>** có generic element type rõ ràng và class **Student** có thể tạo mặc định, biểu thức **students[0].address.city** có cơ hội tạo đủ các nút cần thiết. Với kiểu không xác định, immutable collection, implementation đặc biệt hoặc phần tử không thể khởi tạo, thao tác vẫn có thể thất bại.

**Giới hạn mặc định:** **DataBinder.setAutoGrowCollectionLimit(...)** có mặc định **256**. Điều này giúp tránh yêu cầu độc hại như **students[1000000].name** làm cấp phát collection quá lớn. Có thể giảm theo nghiệp vụ:

~~~java
DataBinder binder = new DataBinder(form, "form");
binder.setAutoGrowCollectionLimit(20); // đặt trước khi binder khởi tạo
~~~

Giới hạn này dành cho việc **tự tăng array/collection**; nó không phải giới hạn độ sâu đường dẫn, giới hạn tổng dung lượng HTTP body hay kiểm tra nghiệp vụ số lượng phần tử. Nên áp dụng thêm kích thước input tối đa, allowed field patterns và validation phù hợp.

**Không tự suy ra Map giống List:** index **[2]** là vị trí có thứ tự đối với list/array; **[KEY]** là key map. Loại map, kiểu key/value và khả năng tạo giá trị mặc định có thể khiến hành vi khác. Khi xây form với collection/map, test chính xác kiểu của property thực tế.

## 8. Tích hợp với Spring MVC và @ModelAttribute

Với một form HTTP truyền tham số:

~~~text
POST /enrollments
Content-Type: application/x-www-form-urlencoded

student.address.city=Hà Nội&student.address.zipCode=100000
~~~

Khi handler dùng **@ModelAttribute**, MVC tạo/lấy model attribute rồi xử lý binding theo cơ chế phù hợp. Trong nhánh **property binding** dựa trên JavaBean, **WebDataBinder** sử dụng cấu hình tương tự **DataBinder**, gồm auto-grow nested paths.

Một controller minh họa trong ứng dụng MVC đã có sẵn:

~~~java
@Controller
class EnrollmentController {

    @InitBinder("enrollmentForm")
    void configure(WebDataBinder binder) {
        // Giới hạn vùng dữ liệu client có thể sửa.
        binder.setAllowedFields(
                "student.address.city",
                "student.address.zipCode");
        binder.setAutoGrowCollectionLimit(20);
        // autoGrowNestedPaths mặc định true trên DataBinder.
    }

    @PostMapping("/enrollments")
    String enroll(
            @ModelAttribute("enrollmentForm") EnrollmentForm form,
            BindingResult result) {
        if (result.hasErrors()) {
            return "enrollment-form";
        }

        // Cần kiểm tra đầy đủ các điều kiện bắt buộc trước khi xử lý.
        return "redirect:/enrollments";
    }
}
~~~

Đây là **đoạn tích hợp minh họa**, cần import **org.springframework.stereotype.Controller**, **org.springframework.web.bind.annotation.InitBinder**, **ModelAttribute**, **PostMapping**, **org.springframework.web.bind.WebDataBinder**, **org.springframework.validation.BindingResult**, và **EnrollmentForm** của dự án. Muốn sử dụng trong ứng dụng thật phải thêm dependency Spring MVC, view **enrollment-form**, xử lý validation và service tương ứng.

Nếu ứng dụng thật **không muốn auto-grow**, có thể chọn **binder.setAutoGrowNestedPaths(false)** tại thời điểm khởi tạo binder, nhưng khi đó phải bảo đảm các nested object cần truy cập đã được tạo bởi ứng dụng hoặc được cung cấp theo cơ chế khởi tạo khác. Không tự đổi mặc định chỉ vì thấy nhiều field null; hãy thiết kế ngữ nghĩa null của form trước.

### Các đường đi khác không được đánh đồng

- **@ModelAttribute / form property binding:** vấn đề của bài này xảy ra ở lúc binder duyệt **student.address.city**.
- **Constructor binding (Spring Framework 6.1+):** **DataBinder.construct(...)** có khả năng tạo object và các constructor argument lồng nhau một cách đệ quy. **setAutoGrowNestedPaths(...)** dành cho setter/field binding, không điều khiển constructor binding. Một DTO **record** thường thuộc nhóm cần xem cách khởi tạo constructor, không phải setter auto-grow.
- **@RequestBody JSON:** **HttpMessageConverter** như Jackson deserialize object graph từ JSON; cấu hình **DataBinder.autoGrowNestedPaths** không phải công tắc chung để Jackson tự sinh object con. JSON có **{"student":null}** và JSON có **{"student":{"address":{"city":"Hà Nội"}}}** là hai đầu vào rất khác nhau.
- **Bean Validation (@Valid/@Validated):** validation đọc/kiểm tra các object đã có. Cascade validation ở property lồng nhau cần **@Valid** và constraint thích hợp; không phải cứ bật **@Valid** thì các object null được Spring DataBinder tạo ra.

Khi thấy một endpoint bind được còn endpoint khác không, hãy kiểm tra **loại input, @ModelAttribute/@RequestBody, kiểu DTO, property binding hay constructor binding, và cấu hình binder** trước khi thay đổi code.

## 9. Ràng buộc đầu vào, validation và bảo mật

Auto-grow là một tiện ích kỹ thuật: client gửi tên field có thể khiến object graph được tạo thêm. Điều này tiện cho form phức tạp nhưng có thể gây tác động không mong muốn nếu bind trực tiếp vào domain entity.

Ví dụ một entity có:

~~~text
account.owner.role
account.billing.limit
account.profile.displayName
~~~

Nếu để client bind mọi public property vào entity, nó có thể cố chỉnh **owner.role** hoặc **billing.limit**, và auto-grow có thể tạo object trung gian để đi tới field nhạy cảm nếu các kiểu cho phép. Do đó:

- **Ưu tiên request DTO chuyên biệt** chỉ khai báo các giá trị mà client có quyền gửi.
- Nếu dùng property binding, đặt **allowedFields** với danh sách rõ ràng; có thể kiểm tra **BindingResult.getSuppressedFields()** để quan sát field bị từ chối.
- Không gắn trực tiếp **@ModelAttribute** vào JPA entity có quan hệ lazy-loaded, owner, role hoặc trạng thái nhạy cảm chỉ để tiết kiệm map DTO. Việc duyệt getter và tự tạo object trong mô hình persistence có thể gây side effect và thay đổi graph ngoài ý định.
- Đặt giới hạn phù hợp cho collection growth và kích thước request. Bảo đảm validation diễn ra sau binding, đặc biệt cho field được auto-grow thành object rỗng.
- **Không dùng ignoreInvalidFields(true) để che lỗi** nếu ứng dụng thực sự cần mọi giá trị đầu vào phải được nhận.

Một DTO có thể khai báo:

~~~java
class EnrollmentRequest {
    @jakarta.validation.Valid
    @jakarta.validation.constraints.NotNull
    private StudentRequest student;
    // getter/setter...
}

class StudentRequest {
    @jakarta.validation.Valid
    @jakarta.validation.constraints.NotNull
    private AddressRequest address;
    // getter/setter...
}

class AddressRequest {
    @jakarta.validation.constraints.NotBlank
    private String city;
    // getter/setter...
}
~~~

Đây là **đoạn minh họa annotation/field**, chưa phải chương trình độc lập. Đặt **@NotNull** trên object trung gian khi không được phép thiếu, **@Valid** để cascade vào object con khi tồn tại, và **@NotBlank** cho chuỗi bắt buộc. Hãy nhớ: **@Valid** một mình không bác bỏ **null**, còn auto-grow có thể tạo object với các property bên trong vẫn null. Việc validation cần provider (chẳng hạn Hibernate Validator) và phải được kích hoạt trong đúng đường xử lý request.

## 10. Chẩn đoán lỗi đường dẫn null

| Hiện tượng | Khả năng nguyên nhân | Cách kiểm tra/xử lý |
| --- | --- | --- |
| **NullValueInNestedPathException** | Một nút trung gian null; auto-grow tắt hoặc không khởi tạo được đối tượng mặc định | Kiểm tra trạng thái cờ, kiểu property, constructor, setter, getter và đường dẫn cụ thể |
| Không báo lỗi nhưng object con vẫn null | Field không được gửi, bị suppressed, bị bỏ qua do cấu hình hoặc luồng xử lý không dùng property binding | Kiểm tra tên request field, **getSuppressedFields()**, **ignoreInvalidFields**, cơ chế bind |
| **NotWritablePropertyException** hoặc lỗi introspection | Tên field sai, thiếu setter, hoặc property không tương thích với cơ chế truy cập | Xác minh JavaBean getter/setter/field và tên đúng chính tả |
| **typeMismatch** | Đường dẫn truy cập được nhưng giá trị không chuyển được sang kiểu property đích | Xem **BindingResult.getFieldErrors()**, converter/formatter, rejected value |
| Collection tăng bất thường hoặc lỗi index | Gửi indexed path quá lớn, cấu trúc collection/kiểu phần tử không thích hợp | Giới hạn collection, kiểm tra kiểu generic và kích thước đầu vào |
| Giá trị trước đó vẫn nằm trong target dù bind có lỗi | Property binding không rollback toàn bộ target | Dùng DTO riêng, kiểm tra tất cả lỗi rồi mới gọi service |
| JSON xử lý khác form | Jackson deserialization không phải cùng đường đi BeanWrapper property binding | Phân biệt **@RequestBody** và **@ModelAttribute** |

**Cách tìm đúng điểm null:** với **student.address.city**, kiểm tra lần lượt **form**, **form.getStudent()**, **form.getStudent().getAddress()**, rồi khả năng ghi **city**. Đừng chỉ log lỗi “city=null” ở cuối vì nó không nói được lỗi do thiếu dữ liệu hợp lệ, thiếu object trung gian hay setter không hoạt động.

Khi exception xuất hiện, chú ý **propertyName/path** mà Spring báo trong lỗi và nguyên nhân gốc (**cause**), đặc biệt trường hợp Spring đã thử tạo object nhưng không tìm được constructor phù hợp. Không nhất thiết mọi lỗi nested null đều là **NullPointerException**; Spring có các exception thuộc hệ thống **BeansException/InvalidPropertyException** để mô tả truy cập property.

## 11. Bài tập và tình huống kiểm thử

Các test có ý nghĩa hơn việc chỉ kiểm tra controller trả HTTP 200:

| Ca kiểm thử | Chuẩn bị | Input | Kết quả mong đợi |
| --- | --- | --- | --- |
| Auto-grow bật | **student=null** | **student.address.city=Hà Nội** | Tạo **Student**, **Address** và gán **city** |
| Auto-grow tắt, nút cha null | **student=null** | **student.address.city=Hà Nội** | Không tự tạo nút cha; xử lý lỗi/field invalid theo API và cấu hình |
| Auto-grow tắt, nút cha có sẵn | **student.address=new Address()** | **student.address.city=Hà Nội** | Bind thành công |
| Nút giữa không thể tạo | **student** hoặc **address** là interface/kiểu không khởi tạo được | Nested path cần đi qua | Không coi là bind thành công; quan sát ngoại lệ phù hợp |
| Leaf có giá trị null | **student.address** có sẵn, **city=null** | Gán giá trị **city** | Gán được nếu accessor/setter hợp lệ |
| Hai nested field cùng cha | **student=null** | **student.address.city** và **student.address.zipCode** | Cùng dùng object **Address** mới tạo |
| Field name không tồn tại | DTO không có **student.planet** | Gửi field đó | Phân biệt ignoreUnknownFields với lỗi null |
| Field bị từ chối | allowedFields chỉ cho phép **student.address.city** | Gửi thêm **student.role** | Role không được bind; kiểm tra suppressed fields |
| Collection index lớn | List rỗng, limit thấp | **students[100000].name** | Không để growth không giới hạn |
| Thiếu trường bắt buộc | Không có nested field nào trong request | Form để trống | Kiểm tra Bean Validation; không suy ra auto-grow sẽ tự tạo object |

Một bài kiểm tra tích hợp Spring MVC nên thử ít nhất một form **@ModelAttribute** và một JSON **@RequestBody**, vì hai tuyến dữ liệu này sử dụng cơ chế tạo object khác nhau. Để chứng minh thiết lập **autoGrowNestedPaths** có tác dụng, dùng đối tượng JavaBean mutable có nested property **null** ngay trước khi bind; test trên object graph đã được khởi tạo sẵn sẽ không phân biệt được bật và tắt.

## 12. Quy tắc thực hành

Khi gặp **“đường dẫn lồng qua đối tượng đang null”**, hãy trả lời theo thứ tự:

1. Đường dẫn được truy cập bởi **DataBinder/BeanWrapper property binding**, constructor binding hay JSON deserialization?
2. Nút nào là **null**: object gốc, object trung gian, phần tử collection hay leaf?
3. **autoGrowNestedPaths** có bật tại accessor thực sự được sử dụng không? Trên **DataBinder chuẩn là true**, trên **BeanWrapperImpl riêng là false**.
4. Kiểu của nút null có thể tạo và gắn trở lại target không? Nếu không, khởi tạo rõ ràng hoặc điều chỉnh DTO/constructor binding.
5. Input có được phép bind vào property đó không, có bị bỏ qua/suppress không, và lỗi có được kiểm tra đầy đủ không?
6. Sau khi bind xong, đã chạy validation và kiểm tra nghiệp vụ trước khi cập nhật trạng thái thật chưa?

Suy nghĩ theo các điểm đó giúp phân biệt lỗi cấu trúc object graph, lỗi chuyển kiểu, lỗi validation và quy tắc nghiệp vụ; đồng thời tránh dựa nhầm vào một mặc định khác giữa **DataBinder** và **BeanWrapperImpl**.

## Tài liệu chính thức

- [Spring Framework 6.2 — Data Binding, property binding và nested paths](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework — DataBinder Javadoc: autoGrowNestedPaths, ignoreInvalidFields, collection limit](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework — BeanWrapperImpl API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/beans/BeanWrapperImpl.html)
- [Spring Framework — NullValueInNestedPathException API](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/beans/NullValueInNestedPathException.html)
- [Spring MVC — @InitBinder và bảo vệ model data binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
