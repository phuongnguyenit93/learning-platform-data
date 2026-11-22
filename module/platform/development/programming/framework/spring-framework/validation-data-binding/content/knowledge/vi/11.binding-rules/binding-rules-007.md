# setIgnoreInvalidFields và đường dẫn không truy cập được trong Spring DataBinder

## 1. Bài toán: một field tồn tại nhưng không đi tới được đối tượng đích

Trong Spring Framework, dữ liệu biểu mẫu có thể mô tả **đường dẫn thuộc tính lồng nhau** thay vì chỉ đặt giá trị cho một field ở cấp đầu tiên. Ví dụ:

~~~text
displayName=An
deliveryAddress.city=Hà Nội
quantity=3
~~~

Giả sử đối tượng `ProfileForm` có field `deliveryAddress` kiểu `Address`, nhưng thuộc tính ấy hiện đang bằng `null`. Tên `deliveryAddress.city` **có ý nghĩa** trong mô hình Java: `ProfileForm` có thuộc tính `deliveryAddress` và `Address` có thuộc tính `city`. Tuy nhiên binder phải đi qua một đoạn đường dẫn đang `null` để đến `city`.

Khi đó có ba câu hỏi khác nhau:

1. Binder có được **tự tạo `Address`** hay không?
2. Nếu không tạo được, binder nên **ném lỗi hay âm thầm bỏ qua** giá trị `deliveryAddress.city`?
3. Nếu tên field hoàn toàn **không tồn tại** (`deliveryAddres.city` sai chính tả), nó có được xử lý như trường hợp số 2 hay không?

`DataBinder.setIgnoreInvalidFields(boolean)` trả lời chủ yếu **câu hỏi số 2**. Muốn hiểu đúng, phải so sánh với `setAutoGrowNestedPaths(...)` và `setIgnoreUnknownFields(...)`, không thể chỉ đọc tên “ignore invalid” rồi nghĩ nó bỏ qua mọi dữ liệu không hợp lệ.

## 2. Định nghĩa chính xác của setIgnoreInvalidFields

`org.springframework.validation.DataBinder` có hai phương thức:

~~~java
binder.setIgnoreInvalidFields(true);
boolean enabled = binder.isIgnoreInvalidFields();
~~~

Trong đó `binder` là một `DataBinder`/`WebDataBinder` đã được tạo. Theo Javadoc Spring:

- **`false` là mặc định.** Không bỏ qua trường không thể truy cập theo kiểu này; việc gắn dữ liệu có thể ném ngoại lệ.
- **`true` cho phép bỏ qua tham số binding đã chỉ tới một thuộc tính có trong mô hình, nhưng phần tương ứng của object graph chưa tồn tại hoặc không truy cập được**, điển hình vì một đoạn nested path chứa `null`.
- Cờ này có tác dụng khi **gắn thuộc tính** qua `bind(PropertyValues)` (setter/field binding). Nó không điều khiển constructor binding qua `construct(ValueResolver)`.
- Cờ này **không áp dụng cho việc đọc lại** property value thông qua `BindingResult` hoặc property accessor, nên “bind đã bỏ qua” không đồng nghĩa “mọi lệnh đọc cùng đường dẫn đều an toàn”.

Ví dụ trực quan:

~~~java
// Đoạn minh họa, các class ProfileForm và Address được định nghĩa ở mục 6.
ProfileForm form = new ProfileForm(); // deliveryAddress == null
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(true);
binder.bind(values); // values chứa "deliveryAddress.city"
~~~

Ở đây `setAutoGrowNestedPaths(false)` làm cho binder **không tự tạo** `Address` khi gặp `null`. Vì `setIgnoreInvalidFields(true)`, giá trị nhập cho `deliveryAddress.city` bị **bỏ qua** trong tình huống nested path null có thể bỏ qua. Sau binding, `form.getDeliveryAddress()` vẫn là `null`.

Điều đặc biệt quan trọng: **bỏ qua không phải là thành công theo nghĩa nghiệp vụ**. Client có thể tưởng rằng địa chỉ đã được cập nhật, nhưng object đích chưa hề nhận giá trị ấy. Vì vậy không nên bật cờ này rộng rãi chỉ để “không còn exception”.

## 3. Ba khái niệm phải tách biệt

| Trường hợp | Ví dụ | Nguyên nhân chính | Cấu hình liên quan |
| --- | --- | --- | --- |
| **Invalid/unreachable field** | `deliveryAddress.city` tồn tại trên class nhưng `deliveryAddress == null`, không auto-grow | Không đi được qua object graph | `setIgnoreInvalidFields` |
| **Unknown field** | `deliveryAdress.city` sai chính tả, hoặc `ghost` không có trên class | Không có thuộc tính đích tương ứng | `setIgnoreUnknownFields` |
| **Type mismatch** | `quantity=abc` trong khi `quantity` là `Integer` | Thuộc tính đích truy cập được nhưng chuỗi không chuyển được sang kiểu yêu cầu | `ConversionService`, `PropertyEditor`/`Formatter`, `BindingResult` |

Ba loại này có **tác động khác nhau**:

- `setIgnoreInvalidFields(true)` **không** biến `quantity=abc` thành một `Integer` hợp lệ và cũng không có nghĩa nó sẽ xóa mọi lỗi `typeMismatch`.
- `setIgnoreUnknownFields(true)` **không** phải là tùy chọn cho đoạn nested path null đã tồn tại về mặt tên/kiểu.
- `setAllowedFields(...)` xác định **những tên field được phép gắn**, là chính sách bảo vệ đầu vào. Nó không thay thế việc xử lý các đoạn null trong object graph.
- `setRequiredFields(...)` kiểm tra sự hiện diện của tên field trong input theo cơ chế riêng; chỉ thấy field được gửi không bảo đảm rằng field đó đã được gắn thành công.

Không nên xem cả bốn tùy chọn là những “nút bỏ qua lỗi” tương đương nhau.

## 4. Tương tác với setAutoGrowNestedPaths

Spring `DataBinder` mặc định có `autoGrowNestedPaths = true`. Khi cấu hình này bật và kiểu đối tượng thích hợp, binder có thể tạo object ở đoạn đường dẫn null để tiếp tục gắn thuộc tính.

Hãy tưởng tượng:

~~~java
public class ProfileForm {
    private Address deliveryAddress;

    public Address getDeliveryAddress() {
        return deliveryAddress;
    }
    public void setDeliveryAddress(Address deliveryAddress) {
        this.deliveryAddress = deliveryAddress;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }
    public void setCity(String city) {
        this.city = city;
    }
}
~~~

Đây là hai class minh họa cần đặt trong tệp phù hợp hoặc khai báo nested class; ví dụ chạy thực sự ở mục 6 sẽ gói chúng vào cùng một tệp Java.

Khi một form mới có `deliveryAddress == null`, bảng sau tóm tắt hành vi **điển hình đối với JavaBean có thể tự khởi tạo**:

| autoGrowNestedPaths | ignoreInvalidFields | Khi bind `deliveryAddress.city=Hà Nội` |
| --- | --- | --- |
| `true` | `false` (mặc định) | Spring có thể tạo `Address`, sau đó gắn `city`. Không có đường dẫn null chưa được giải quyết |
| `true` | `true` | Vẫn có thể tự tạo và gắn bình thường; cờ ignore không có tác dụng nếu đường dẫn đã truy cập được |
| `false` | `false` | Đường dẫn null không tự tạo; thường ném `NullValueInNestedPathException` |
| `false` | `true` | Không tự tạo; giá trị cho nested path null có thể bị bỏ qua và các field hợp lệ khác vẫn được xử lý |

Hai điểm dễ gây nhầm:

**Thứ nhất**, `setIgnoreInvalidFields(true)` không tắt auto-grow. Nếu vẫn để mặc định `autoGrowNestedPaths=true`, Spring có thể tạo `Address` và gắn field, nên bạn không quan sát được hành vi “ignore”. Muốn thấy sự khác biệt, cần mô hình thích hợp và tắt auto-grow **trước khi binding**.

**Thứ hai**, `autoGrowNestedPaths=true` không có nghĩa Spring luôn tạo được mọi loại object. Constructor không phù hợp, abstract type, kiểu collection không khởi tạo được, quyền truy cập, cấu trúc immutable hoặc setter lỗi vẫn có thể gây exception khác. Cờ ignore được thiết kế cho **lỗi đường dẫn null có thể bỏ qua**, không bảo đảm nuốt mọi ngoại lệ phát sinh từ code của setter, converter hoặc domain model.

### 4.1. Lưu ý về thời điểm cấu hình

~~~java
DataBinder binder = new DataBinder(form, "profileForm");
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(true);
// Bây giờ mới binder.bind(...)
~~~

Với `setAutoGrowNestedPaths`, nên cấu hình trước khi binder đã khởi tạo `BindingResult`/accessor hoặc thực hiện các bước binding khác. Một số phiên bản Spring chủ động từ chối đổi cấu hình auto-grow sau khi binder đã khởi tạo vì sẽ làm hành vi không nhất quán. Trong Spring MVC, đặt các thiết lập tại `@InitBinder` để framework làm binding sau đó.

## 5. Điều gì thực sự bị bỏ qua trong PropertyAccessor?

Bên dưới `DataBinder`, `BeanWrapper`/`PropertyAccessor` xử lý tập `PropertyValues`. Đối với tình huống nested path null trong quá trình `setPropertyValues`, lớp accessor có thể tạo `NullValueInNestedPathException`.

Ở các dòng Spring hiện đại, logic quan trọng là:

~~~text
for mỗi propertyValue cần gắn:
    try setPropertyValue(...)
    nếu NotWritablePropertyException:
        nếu ignoreUnknown = true thì bỏ qua
        ngược lại ném exception
    nếu NullValueInNestedPathException:
        nếu ignoreInvalid = true thì bỏ qua
        ngược lại ném exception
    nếu PropertyAccessException có thể gom:
        tích lũy lỗi chuyển kiểu / truy cập tương ứng
sau vòng lặp:
    nếu có lỗi gom được, ném PropertyBatchUpdateException
~~~

Đây là **pseudocode mô tả**, không phải mã nguồn đầy đủ. `DataBinder` tiếp nhận `PropertyBatchUpdateException` và chuyển các lỗi thuộc nhóm được gom sang cơ chế lỗi trong `BindingResult` qua `BindingErrorProcessor`. Các `BeansException` khác, chẳng hạn nested path null không được phép bỏ qua, có thể thoát khỏi `bind(...)` trực tiếp.

### 5.1. Vì sao BindingResult có thể không báo lỗi?

Nếu cấu hình:

~~~java
binder.setAutoGrowNestedPaths(false);
binder.setIgnoreInvalidFields(true);
~~~

và field duy nhất bị lỗi là một đường dẫn null đã được phép bỏ qua, `binder.getBindingResult().hasErrors()` có thể là **false**. Không có `FieldError` chỉ vì một field bị bỏ qua bằng ignore-invalid. Cũng không nên dùng `getSuppressedFields()` để đếm những field bị ignore theo cách này: suppressed fields là thông tin liên quan đến **allowed/disallowed field filtering**, một cơ chế khác.

Đây là lý do rất đáng chú ý khi xây REST/form API: một handler chỉ kiểm tra `BindingResult.hasErrors()` có thể đi tiếp và lưu một object thiếu cập nhật mà người dùng thực tế đã gửi.

### 5.2. Ignore-invalid không đồng nghĩa ignore mọi lỗi nested path

Tên thuộc tính sai có thể tạo `NotWritablePropertyException`; trường đúng nhưng setter cố ý ném lỗi có thể tạo ngoại lệ khác; giá trị sai kiểu có thể tạo `TypeMismatchException` hoặc lỗi conversion tương ứng. Không nên bật `setIgnoreInvalidFields(true)` với kỳ vọng framework sẽ nuốt **mọi** loại exception đó.

Lựa chọn hành vi nên dựa trên **loại lỗi thực tế** và tính chất nghiệp vụ của form.

## 6. Ví dụ Java 17+ chạy được với DataBinder

Chương trình dưới đây không cần servlet hoặc Spring Boot. Nó dùng `DataBinder` độc lập để minh họa:

1. Mặc định `ignoreInvalidFields = false` và `autoGrowNestedPaths = true`.
2. Tắt auto-grow, bật ignore-invalid: nested path null bị bỏ qua **nhưng field cấp đầu vẫn được gắn**.
3. Tắt cả hai: `NullValueInNestedPathException` xuất hiện.
4. Bật auto-grow: nested object được tạo và field được gắn thành công.
5. Giá trị sai kiểu vẫn tạo lỗi binding dù ignore-invalid bật.
6. `setAllowedFields` hoạt động như một whitelist khác với ignore-invalid.

Ví dụ dùng Spring Framework `7.0.9` để mã nguồn không phụ thuộc phiên bản “mới nhất” có thể thay đổi. Dùng JDK 17+ và Maven. Các đầu ra được kiểm tra về mặt logic theo API Spring; tùy environment, Maven có thể in thêm log riêng.

### 6.1. Cấu trúc

~~~text
invalid-fields-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── InvalidFieldsDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>invalid-fields-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` kéo theo các module Spring dùng cho `DataBinder` và JavaBean binding. Trong dự án Spring Boot có dependency management, nên dùng các phiên bản Spring do Boot BOM cung cấp thay vì tùy ý trộn module.

### 6.3. src/main/java/InvalidFieldsDemo.java

~~~java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.NullValueInNestedPathException;
import org.springframework.validation.DataBinder;

public class InvalidFieldsDemo {

    public static class Address {
        private String city;

        public Address() {
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public static class ProfileForm {
        private Address deliveryAddress;
        private String note;
        private Integer quantity;

        public ProfileForm() {
        }

        public Address getDeliveryAddress() {
            return deliveryAddress;
        }

        public void setDeliveryAddress(Address deliveryAddress) {
            this.deliveryAddress = deliveryAddress;
        }

        public String getNote() {
            return note;
        }

        public void setNote(String note) {
            this.note = note;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

    private static MutablePropertyValues values(String... pairs) {
        if (pairs.length % 2 != 0) {
            throw new IllegalArgumentException("Field/value pairs required");
        }
        MutablePropertyValues pvs = new MutablePropertyValues();
        for (int i = 0; i < pairs.length; i += 2) {
            pvs.add(pairs[i], pairs[i + 1]);
        }
        return pvs;
    }

    public static void main(String[] args) {
        // 1. Giá trị mặc định, trước khi tùy chỉnh binder.
        DataBinder defaults = new DataBinder(new ProfileForm(), "profileForm");
        System.out.println("default.ignoreInvalid="
                + defaults.isIgnoreInvalidFields());
        System.out.println("default.autoGrow="
                + defaults.isAutoGrowNestedPaths());

        // 2. Không auto-grow, nhưng bỏ qua nested path null.
        ProfileForm optional = new ProfileForm();
        DataBinder lenient = new DataBinder(optional, "profileForm");
        lenient.setAutoGrowNestedPaths(false);
        lenient.setIgnoreInvalidFields(true);
        lenient.bind(values(
                "deliveryAddress.city", "Ha Noi",
                "note", "Accepted"
        ));
        System.out.println("lenient.addressNull="
                + (optional.getDeliveryAddress() == null));
        System.out.println("lenient.note=" + optional.getNote());
        System.out.println("lenient.hasErrors="
                + lenient.getBindingResult().hasErrors());
        System.out.println("lenient.suppressed="
                + lenient.getBindingResult().getSuppressedFields().length);

        // 3. Không auto-grow và không bỏ qua đường dẫn null.
        ProfileForm strictForm = new ProfileForm();
        DataBinder strict = new DataBinder(strictForm, "profileForm");
        strict.setAutoGrowNestedPaths(false);
        strict.setIgnoreInvalidFields(false);
        try {
            strict.bind(values("deliveryAddress.city", "Ha Noi"));
            System.out.println("strict.exception=none");
        } catch (NullValueInNestedPathException ex) {
            System.out.println("strict.exception="
                    + ex.getClass().getSimpleName());
        }

        // 4. Auto-grow tạo Address dù ignore-invalid = false.
        ProfileForm grown = new ProfileForm();
        DataBinder growing = new DataBinder(grown, "profileForm");
        growing.setAutoGrowNestedPaths(true);
        growing.setIgnoreInvalidFields(false);
        growing.bind(values("deliveryAddress.city", "Ha Noi"));
        System.out.println("grow.city="
                + grown.getDeliveryAddress().getCity());
        System.out.println("grow.hasErrors="
                + growing.getBindingResult().hasErrors());

        // 5. Type mismatch không biến mất bởi ignore-invalid.
        ProfileForm invalidNumber = new ProfileForm();
        DataBinder mismatch = new DataBinder(invalidNumber, "profileForm");
        mismatch.setIgnoreInvalidFields(true);
        mismatch.bind(values("quantity", "not-a-number"));
        System.out.println("mismatch.quantity="
                + invalidNumber.getQuantity());
        System.out.println("mismatch.fieldError="
                + mismatch.getBindingResult().hasFieldErrors("quantity"));

        // 6. Whitelist: một field bị chặn không phải "ignored invalid".
        ProfileForm restricted = new ProfileForm();
        DataBinder allowlisted = new DataBinder(restricted, "profileForm");
        allowlisted.setAllowedFields("note");
        allowlisted.bind(values(
                "note", "Approved",
                "quantity", "99"
        ));
        System.out.println("allowlist.note=" + restricted.getNote());
        System.out.println("allowlist.quantity="
                + restricted.getQuantity());
        System.out.println("allowlist.suppressed="
                + allowlisted.getBindingResult().getSuppressedFields().length);
    }
}
~~~

### 6.4. Chạy và kiểm tra stdout

Tại thư mục `invalid-fields-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=InvalidFieldsDemo
~~~

Kết quả kỳ vọng từ `System.out.println` của chương trình (không tính Maven logs):

~~~text
default.ignoreInvalid=false
default.autoGrow=true
lenient.addressNull=true
lenient.note=Accepted
lenient.hasErrors=false
lenient.suppressed=0
strict.exception=NullValueInNestedPathException
grow.city=Ha Noi
grow.hasErrors=false
mismatch.quantity=null
mismatch.fieldError=true
allowlist.note=Approved
allowlist.quantity=null
allowlist.suppressed=1
~~~

Phân tích từng trường hợp:

- **Mặc định:** `isIgnoreInvalidFields() == false`; `isAutoGrowNestedPaths() == true` ở `DataBinder` tiêu chuẩn.
- **Lenient:** vì auto-grow bị tắt nên `deliveryAddress` vẫn là null. Đường dẫn `deliveryAddress.city` được bỏ qua do ignore-invalid, nhưng `note` là field cấp đầu và vẫn nhận `Accepted`. `hasErrors=false` và `suppressed=0` nhấn mạnh rằng ignore-invalid **không phải** allowed-fields filtering.
- **Strict:** đường dẫn `deliveryAddress.city` không thể đi qua `deliveryAddress == null` khi auto-grow tắt. `NullValueInNestedPathException` được ném và bị bắt ngay trong chương trình.
- **Grow:** đối tượng `Address` có constructor không tham số và getter/setter hợp lệ, nên Spring tạo instance, đi đến `city` và gắn `Ha Noi`; không cần ignore-invalid.
- **Mismatch:** `quantity` truy cập được nhưng `not-a-number` không chuyển được thành `Integer`. Lỗi chuyển kiểu được ghi vào `BindingResult`/`FieldError`, `quantity` tiếp tục null.
- **Allowlist:** chỉ `note` được phép property-bind. `quantity` trong request bị chặn bởi whitelist, giá trị đích không đổi và tên field bị ghi nhận trong `getSuppressedFields()`.

Điểm thực hành hữu ích: chương trình không trộn chung tất cả config trong một binder, vì như vậy rất khó xác định **cấu hình nào gây ra kết quả nào**.

### 6.5. Những trường hợp mã mẫu không cố khẳng định

- Không khẳng định mọi kiểu nested object đều tự được tạo: constructor, generic type, collection/index, access mode và custom accessor đều có thể đổi kết quả.
- Không khẳng định mọi lỗi property binding đều có cùng class exception: chương trình chỉ bắt **trường hợp null nested path đã chủ động tạo**.
- Không khẳng định ignore-invalid sẽ bỏ qua field sai kiểu, field không tồn tại hay lỗi domain trong setter.
- Không khẳng định stdout là bằng chứng đã chạy Maven trong môi trường hiện tại; cần chạy lệnh trên để xác minh đúng phiên bản dependency và JDK bạn dùng.

## 7. Phân biệt setIgnoreUnknownFields

`setIgnoreUnknownFields(boolean)` xử lý **tên field không có đối ứng trên target class**, không xử lý đường dẫn null của một field **đã được định nghĩa**.

Ví dụ:

~~~text
deliveryAddress.city=Da Nang  # Nested path hợp lệ theo tên, nhưng Address có thể null
deliveryAdress.city=Da Nang   # "Address" bị viết sai: property không tồn tại
unknownFlag=on               # Không có field unknownFlag trên ProfileForm
~~~

| Cấu hình | Giá trị mặc định | Trường hợp xử lý chính |
| --- | --- | --- |
| `setIgnoreInvalidFields(false)` | `false` | Không nuốt lỗi nested path null chưa truy cập được |
| `setIgnoreInvalidFields(true)` | Không mặc định | Bỏ qua nested path null phù hợp trong quá trình `bind` |
| `setIgnoreUnknownFields(true)` | `true` | Bỏ qua tên field không tồn tại trên target |
| `setIgnoreUnknownFields(false)` | Không mặc định | Khi request chứa field không tồn tại, có thể ném `NotWritablePropertyException` |

Nếu bạn muốn client nhận thông báo khi gõ nhầm tên field, có thể cân nhắc `setIgnoreUnknownFields(false)` **trong luồng property binding phù hợp**, song cần chuẩn bị xử lý exception. Nếu API cố ý hỗ trợ gửi nhiều field phụ không dùng, có thể giữ mặc định nhưng phải hiểu rằng các field này không được gắn.

Một lỗi thường gặp là nhìn thấy cả hai config đều có chữ “ignore”, rồi bật cả hai để giảm số lỗi. Kết quả có thể là **client gửi sai và server yên lặng bỏ qua**, gây khó debug hoặc làm lệch trạng thái ứng dụng.

### 7.1. getSuppressedFields không phải danh sách mọi trường bị bỏ qua

`BindingResult.getSuppressedFields()` hữu ích để phát hiện field được gửi nhưng bị loại bởi cấu hình allowed/disallowed field của binder:

~~~java
binder.setAllowedFields("displayName", "note");
binder.bind(values);
String[] suppressed = binder.getBindingResult().getSuppressedFields();
~~~

Đây là đoạn minh họa với biến `values` đã được xây dựng. Nếu field bị loại bởi policy, Spring có thể ghi tên vào danh sách suppressed. **Không** dùng danh sách đó để kết luận không có field bị ignore do `setIgnoreInvalidFields(true)` hay do `setIgnoreUnknownFields(true)`. Hai trường hợp ignore không bắt buộc tạo suppressed entry.

## 8. Trường hợp dùng trong Spring MVC với @InitBinder

Đối với input qua HTML form hoặc request parameters, `@ModelAttribute` thường dùng cơ chế `WebDataBinder`. Có thể cấu hình tại controller:

~~~java
// Đoạn minh họa trong controller; ProfileForm và view/service phải có sẵn.
@Controller
class ProfileController {

    @InitBinder("profileForm")
    void configureForm(WebDataBinder binder) {
        binder.setAutoGrowNestedPaths(false);
        binder.setIgnoreInvalidFields(false);
        binder.setIgnoreUnknownFields(false);
        binder.setAllowedFields(
                "displayName", "deliveryAddress.city", "note");
    }

    @PostMapping("/profiles")
    String submit(
            @Valid @ModelAttribute("profileForm") ProfileForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "profile-form";
        }
        profileService.save(form);
        return "redirect:/profiles";
    }
}
~~~

Mã ở đây **chỉ minh họa cấu hình binder**, không tự biên dịch nếu thiếu imports, các thành phần service/view và model. Lưu ý thiết kế này còn một vấn đề cần xử lý: `setAutoGrowNestedPaths(false)` và `ignoreInvalidFields=false` có thể khiến request chứa `deliveryAddress.city` ném **ngoại lệ** khi `deliveryAddress` đang null, chứ không nhất thiết tạo `FieldError` rồi chạy nhánh `result.hasErrors()`.

Vì vậy có ít nhất hai chiến lược thiết kế hợp lý:

**Chiến lược A — Tạo đầy đủ object graph phù hợp trước khi binding.** Ví dụ `ProfileForm` khởi tạo `deliveryAddress = new Address()`, giữ `autoGrowNestedPaths=false`. Binder không phải tự tạo `Address` và có thể gắn `city`. Thích hợp khi form luôn có một `Address` hợp lệ trong mô hình.

**Chiến lược B — Cho phép auto-grow có kiểm soát.** Giữ `setAutoGrowNestedPaths(true)` để framework tạo nested object, nhưng giới hạn field cho phép và dùng DTO/form object rõ ràng. Cần xem tác động của array/list index và `autoGrowCollectionLimit` nếu form chứa collection do client có thể điều khiển.

**Chiến lược C — Cố ý bỏ qua field nested của phần chưa tồn tại.** Có thể dùng `setIgnoreInvalidFields(true)`, nhưng chỉ khi quy ước nghiệp vụ nói rõ “nếu nhánh object chưa tồn tại thì field đó không được cập nhật”; giao diện/handler phải nhận biết điều này, không trả thông báo “đã cập nhật” cho một field thực tế không được áp dụng.

Với API quản lý dữ liệu quan trọng, **ưu tiên báo lỗi rõ ràng hoặc ánh xạ input tường minh**, thay vì âm thầm bỏ qua một yêu cầu sửa đổi.

### 8.1. Không nhầm @ModelAttribute với @RequestBody

~~~java
@PostMapping("/profiles/json")
void updateJson(@Valid @RequestBody UpdateProfileRequest request) {
    service.update(request);
}
~~~

Đây là ví dụ phương thức controller không độc lập. `@RequestBody` JSON thường được deserialize bằng `HttpMessageConverter`/Jackson, **không** dùng cơ chế `DataBinder.bind(PropertyValues)` cho từng tham số dạng `deliveryAddress.city`. `setIgnoreInvalidFields` không phải cờ để bỏ qua thuộc tính JSON nested null hoặc unknown JSON properties. Với JSON, hãy cấu hình DTO, Jackson, Bean Validation và mapping vào domain model theo đúng hợp đồng.

Cũng cần nhớ: constructor binding của `DataBinder.construct(...)` là cơ chế riêng, **không** dùng `setIgnoreInvalidFields` như property binding.

## 9. Đường dẫn null, collection index, object graph và ranh giới bảo mật

### 9.1. Một nested field có thể được khai báo nhưng không tồn tại tại runtime

Các đường dẫn như:

~~~text
customer.address.city
lines[2].product.code
preferences.theme.name
~~~

đều yêu cầu đi qua từng đoạn object/list. Lỗi có thể bắt nguồn từ:

- Một object trung gian là `null`.
- Collection chưa được khởi tạo hoặc index chưa tồn tại và auto-growth bị tắt hoặc vượt ngưỡng.
- Kiểu phần tử không biết cách tạo, collection bất biến hoặc custom collection không hoạt động như Java `List` thông thường.
- Path hợp lệ trên class nhưng không được phép truy cập qua mô hình accessor thực tế.
- Setter/constructor có hành vi hoặc ràng buộc làm thao tác không thể hoàn thành.

Chỉ **một phần** các trường hợp sẽ thuộc dạng `NullValueInNestedPathException` mà ignore-invalid có thể bỏ qua. Với out-of-bounds index, unknown property, accessor lỗi và conversion lỗi, cần kiểm tra riêng exception/API theo phiên bản. Không nên giả định “mọi path không tới được đều bị ignore khi true”.

### 9.2. Quan hệ với autoGrowCollectionLimit

`setAutoGrowCollectionLimit(int)` quản lý ngưỡng tự mở rộng array/list trong các chế độ được phiên bản Spring hỗ trợ. Nó không phải cách khác để bật/tắt ignore-invalid. Nếu đường dẫn `lines[100].sku` vượt ngưỡng hoặc không mở rộng được, kết quả còn phụ thuộc collection, index, access mode và cấu hình. **Đừng mặc định** rằng `setIgnoreInvalidFields(true)` sẽ biến mọi out-of-range index thành một field bị bỏ qua an toàn.

Đối với request lớn hoặc path do client tự gửi, hãy giới hạn kích thước/body, độ sâu path, số field, số phần tử và các field được phép thay đổi. Validation `@Size` có thể chạy **sau khi binding**, nên không thay thế kiểm soát tài nguyên trong bước phân tích dữ liệu.

### 9.3. Cờ ignore không phải chính sách authorization

`setIgnoreInvalidFields` được thiết kế để quyết định **cách xử lý đường dẫn không truy cập được**, không quyết định ai có quyền đổi field nào. Bật true không ngăn mass assignment vào field nội bộ nếu field ấy thực sự có đường dẫn hợp lệ và truy cập được.

Ví dụ `role=ADMIN` trên một entity có `setRole(...)` hợp lệ vẫn có thể được gắn vào khi không có allowlist. Hàng rào quan trọng hơn là:

1. DTO/form object **riêng cho input** với đúng tập field có thể ghi.
2. `setAllowedFields(...)` khi áp dụng property binding.
3. Kiểm tra quyền của người gọi và bất biến domain tại service.
4. Chặn hoặc báo lỗi rõ ràng đối với field bị bỏ qua trái mong đợi.
5. Test các request gửi field bất thường và nested path null.

Không được biến “không có lỗi binding” thành “request đã thực hiện đầy đủ theo ý định” khi một số tham số đã bị ignore.

## 10. Cách kiểm thử có hệ thống

Khi viết test cho một controller/form object, hãy kiểm tra **trạng thái object sau binding** cùng với ngoại lệ và `BindingResult`, thay vì chỉ nhìn HTTP status.

| Test case | Thiết lập | Kết luận cần kiểm chứng |
| --- | --- | --- |
| Nested field tồn tại, nhánh null, auto-grow tắt | `ignoreInvalid=false` | Lỗi đường dẫn không bị âm thầm bỏ qua |
| Nested field tồn tại, nhánh null, auto-grow tắt | `ignoreInvalid=true` | Input nested bị bỏ qua; field độc lập vẫn gắn; không mặc định có `FieldError` |
| Nested field tồn tại, nhánh null, auto-grow bật | Kiểu có constructor phù hợp | Nhánh object có thể được tạo và field được gắn |
| Sai kiểu số | `quantity=abc` | `hasFieldErrors("quantity")` phản ánh conversion error |
| Field không tồn tại | `ignoreUnknown=true/false` | Hành vi khác invalid-nested; không nhầm tên field |
| Field bị chặn bởi allowlist | `setAllowedFields("note")` | Field không được gắn và có thể xuất hiện trong `getSuppressedFields()` |
| Field đã gửi nhưng bị ignore | `ignoreInvalid=true` | UI/service không mặc định coi thao tác cập nhật đã thành công |
| JSON request nested | `@RequestBody` | Cấu hình Jackson và validation được kiểm riêng, không suy diễn từ `DataBinder.bind` |

Các kiểm tra trên có thể chạy bằng unit test với `DataBinder` như chương trình ở mục 6. Nếu muốn kiểm tra Spring MVC thật, dùng `MockMvc` cùng form parameters, exception resolver và view/model phù hợp. Kết quả HTTP phụ thuộc handler, global exception handler và cấu hình cụ thể: không có quy tắc “ignore-invalid false = HTTP 400” áp dụng vô điều kiện.

Trong production, nên log thông tin cấu trúc field sai theo cách an toàn và tránh log dữ liệu cá nhân hoặc secret. Không trực tiếp in `rejectedValue` hoặc toàn bộ request body vào log mà không có chính sách masking.

## 11. Các lỗi thường gặp và cách sửa

1. **Bật ignore-invalid để che mọi lỗi.** Hãy phân loại unknown path, null nested, type mismatch và lỗi domain trước khi chọn chính sách.
2. **Quên auto-grow mặc định bật.** Với object có thể tạo, nested null sẽ được auto-grow nên khó quan sát effect của ignore-invalid. Test cả hai cấu hình.
3. **Tưởng true đồng nghĩa với @Valid.** `setIgnoreInvalidFields` xử lý binding, không chạy `Validator` và không xác nhận dữ liệu hợp lệ.
4. **Tưởng ignored field luôn có FieldError.** Một field null nested bị ignore có thể không để lại lỗi trong `BindingResult`. Kiểm tra object và chính sách ứng dụng.
5. **Tưởng getSuppressedFields liệt kê mọi ignored field.** Danh sách này gắn với allowed/disallowed field filtering, không phải lịch sử đầy đủ mọi giá trị bị bỏ qua.
6. **Bật ignoreUnknown thay cho ignoreInvalid.** Một property sai tên khác với property tồn tại nhưng đường dẫn chưa khởi tạo.
7. **Không xử lý exception khi cấu hình strict.** `NullValueInNestedPathException` có thể thoát từ `bind(...)`, không nhất thiết đi vào `BindingResult`.
8. **Đọc nested field sau khi bind mà tưởng ignore vẫn áp dụng.** Cờ này không bảo vệ mọi lệnh đọc qua `getBindingResult()` hoặc property accessor.
9. **Cho client bind trực tiếp entity.** Quy tắc ignore không thay cho DTO, allowlist, kiểm tra quyền hay bất biến domain.
10. **Dùng cùng cấu hình cho cả form và JSON.** `@ModelAttribute`/property binding khác `@RequestBody`/Jackson; hãy xử lý từng lối vào đúng cơ chế.
11. **Giữ nhánh nested null ngoài ý muốn.** Nếu phần nested luôn phải tồn tại, khởi tạo trong constructor/model factory hoặc thiết kế DTO rõ ràng, thay vì bỏ qua input mà không báo.
12. **Xem một cờ ignore như cách giảm DoS.** Nó không phải giới hạn số field, độ sâu đường dẫn, chỉ số collection hay số bytes.
13. **Tắt auto-grow sau khi binder đã khởi tạo.** Cấu hình từ sớm, ở điểm xây dựng binder hoặc `@InitBinder`.
14. **Không test phiên bản framework đang chạy.** Behavior với nested collection/custom type/constructor và chính sách exception có thể khác; cần regression test các path thực tế của ứng dụng.

## 12. Checklist áp dụng vào dự án

Trước khi bật `setIgnoreInvalidFields(true)`, hãy trả lời:

- Field nào được xem là **tùy chọn** khi nhánh nested object chưa tồn tại?
- Nếu client gửi field ấy nhưng server bỏ qua, API sẽ báo gì để không tạo hiểu lầm?
- Nhánh null có nên được **tạo** trước binding thay vì ignore?
- Controller đang dùng `@ModelAttribute`/form binding hay `@RequestBody` JSON?
- Cấu hình `autoGrowNestedPaths` hiện tại là gì?
- Có whitelist các field được phép sửa không? Có cần cảnh báo field bị suppressed không?
- Lỗi nested null nào phải là lỗi nghiệp vụ, và lỗi nào có thể bỏ qua an toàn?
- Test đã đối chiếu object sau binding, `BindingResult` và exception chưa?
- Có giới hạn số phần tử và độ sâu của input không?

Một quy tắc thiết kế thực dụng: **nếu người dùng đã gửi giá trị cần được áp dụng, đừng âm thầm bỏ qua nó**. Chỉ bật ignore-invalid cho những luồng đã định nghĩa rõ “nhánh nested chưa tồn tại thì input tương ứng có thể bị bỏ qua”. Trong các form thông thường, khởi tạo object graph hợp lệ, dùng DTO rõ ràng hoặc báo lỗi cụ thể thường dễ vận hành hơn.

## Tóm tắt

`setIgnoreInvalidFields(true)` là tùy chọn **bỏ qua một số tham số property binding trỏ tới field có tên hợp lệ nhưng không truy cập được**, điển hình vì null trong nested path. Nó **mặc định tắt**, không tạo object lồng nhau, không chuyển lỗi sai kiểu thành dữ liệu hợp lệ và không thay thế `setIgnoreUnknownFields`, `setAllowedFields` hoặc validation. `autoGrowNestedPaths` quyết định binder có cố lấp nhánh null để đi tiếp hay không; nếu nó tạo được object, cờ ignore-invalid có thể không cần tác dụng.

Phân biệt ba kết quả **đã gắn được**, **bị bỏ qua**, **thất bại với lỗi/ngoại lệ** là chìa khóa để không làm mất input một cách im lặng khi sử dụng DataBinder.

## Tài liệu tham khảo

- Spring Framework 6.2 — `DataBinder` Javadoc (setIgnoreInvalidFields, ignoreUnknownFields, autoGrowNestedPaths): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 7.0 — `DataBinder` Javadoc: https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — JavaBeans và đường dẫn thuộc tính: https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html
- Spring Framework — `AbstractPropertyAccessor.setPropertyValues` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/AbstractPropertyAccessor.html
- Spring Framework — `@InitBinder` trong Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
