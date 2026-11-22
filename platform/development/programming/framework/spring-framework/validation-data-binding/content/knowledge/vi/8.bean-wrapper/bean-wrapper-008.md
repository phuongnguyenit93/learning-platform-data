# initBeanPropertyAccess và initDirectFieldAccess của DataBinder

## 1. Vì sao DataBinder có hai chế độ truy cập?

Trong Spring Framework, **DataBinder** gắn các giá trị đầu vào (property values) vào đối tượng Java. Khi đặt một giá trị cho thuộc tính, Spring phải chọn **đường truy cập** đến dữ liệu bên trong đối tượng:

- Qua **thuộc tính JavaBeans**, thường đi qua phương thức **setXxx(...)** và đọc qua **getXxx()** hoặc **isXxx()**.
- Qua **field trực tiếp**, dùng cơ chế phản chiếu (reflection) để đặt giá trị vào trường dữ liệu, không gọi setter.

Hai phương thức chọn chế độ này là **initBeanPropertyAccess()** và **initDirectFieldAccess()** của **org.springframework.validation.DataBinder**. Chúng thay đổi cách **property binding** truy cập đối tượng, chứ không phải hai annotation, hai kiểu validation hay hai cách nhận HTTP khác nhau.

Ví dụ, đối tượng nhận dữ liệu có setter chuyển tên sang chữ hoa:

~~~java
public void setDisplayName(String input) {
    this.displayName = input.strip().toUpperCase(java.util.Locale.ROOT);
}
~~~

Nếu gắn tên **"  Lan  "** qua chế độ JavaBeans, setter có thể lưu **"LAN"**. Nếu gắn cùng tên qua chế độ direct field, setter bị bỏ qua và field có thể giữ nguyên **"  Lan  "**. Đó là khác biệt về hành vi ứng dụng, không chỉ là khác biệt về cú pháp.

Chế độ JavaBeans là **mặc định** của DataBinder. Direct field access là lựa chọn chuyên biệt, chỉ nên dùng khi có lý do rõ ràng và dữ liệu/đối tượng nằm trong phạm vi tin cậy. Spring cảnh báo không sử dụng direct field access để bind dữ liệu đến từ nguồn không tin cậy. Nguyên nhân được trình bày ở phần bảo mật bên dưới.

## 2. Mô hình hoạt động bên trong

Với một DataBinder đã có target object, mô hình khái quát là:

~~~text
                       new DataBinder(target, "profile")
                                      |
                       +--------------+--------------+
                       |                             |
              Mặc định hoặc gọi              Gọi initDirectFieldAccess()
             initBeanPropertyAccess()
                       |                             |
             BeanPropertyBindingResult       DirectFieldBindingResult
                       |                             |
                 BeanWrapperImpl              DirectFieldAccessor
                       |                             |
             Tìm thuộc tính JavaBeans        Tìm field qua reflection
                       |                             |
                 Gọi setXxx(...)              Ghi trực tiếp vào field
                       +--------------+--------------+
                                      |
                         Chuyển kiểu khi cần thiết
                         và thu thập BindingResult
~~~

Đây là sơ đồ khái niệm. Việc chuyển kiểu có thể diễn ra khi giải quyết phép gán, trước khi giá trị được ghi vào target. Một nguồn đầu vào có thể đã là đúng kiểu Java nên không cần chuyển thêm.

**initBeanPropertyAccess():**

- Yêu cầu DataBinder sử dụng lối truy cập JavaBeans dựa trên property descriptor và **BeanWrapper**.
- Là chế độ mặc định. Thường chỉ cần tạo **new DataBinder(target, name)** và gọi **bind(...)**; gọi phương thức này một cách tường minh là tùy chọn.
- Giá trị được đưa qua setter tương ứng nếu thuộc tính có thể ghi. Getter hỗ trợ việc đọc và điều hướng đường dẫn thuộc tính; không phải mọi lần ghi đều buộc phải gọi getter.
- Setter có thể chuẩn hóa, ghi log, thay đổi field liên quan hoặc thực hiện kiểm tra riêng. Tuy nhiên không nên coi setter là biện pháp bảo mật/validation duy nhất.

**initDirectFieldAccess():**

- Yêu cầu DataBinder dùng **DirectFieldAccessor** truy cập trực tiếp tới field của đối tượng.
- Không cần **setXxx(...)** cho field được phép bind; có thể ghi vào field **private** thông qua reflection trong những trường hợp Java cho phép.
- Không gọi logic bên trong setter; có thể ghi dữ liệu vốn không được thiết kế là thuộc tính JavaBeans có thể sửa.
- Không đồng nghĩa mọi field đều luôn có thể ghi: hạn chế của reflection, module access, kiểu bất biến/final, chính sách allowed fields và cấu trúc target vẫn tồn tại.
- **Chỉ sử dụng trong tình huống tin cậy**; đặc biệt không bật direct field access để nhận tham số HTTP hoặc input bên ngoài không đáng tin.

Khi gọi **getBindingResult()**, **bind(...)** hoặc một thao tác khác khiến bộ truy cập/binding result nội bộ được tạo, DataBinder đã xác lập cách truy cập. Hãy chọn chế độ **ngay sau khi tạo binder, trước khi bind hay truy cập BindingResult**, và tạo một DataBinder mới nếu cần chế độ khác.

## 3. So sánh có hệ thống

| Tiêu chí | initBeanPropertyAccess() | initDirectFieldAccess() |
| --- | --- | --- |
| Mặc định của DataBinder | Có | Không |
| Cơ chế truy cập | Thuộc tính JavaBeans / BeanWrapper | Field trực tiếp / DirectFieldAccessor |
| Cần setter để gán property thông thường | Có, đối với thuộc tính chỉ được ghi bằng setter | Không cần setter |
| Gọi logic trong setter | Có | Không |
| Bind field private không có setter | Không phải thuộc tính JavaBeans có thể ghi | Có thể khi reflection cho phép |
| Giá trị có thể bị setter chuẩn hóa/biến đổi | Có | Không thông qua setter |
| Cần cấu hình conversion nếu kiểu không khớp | Có thể | Có thể |
| Lỗi chuyển kiểu/ghi field | Thu thập qua BindingResult theo quy tắc binder | Tương tự, nhưng điểm truy cập khác |
| Hỗ trợ nested property path | Có, theo BeanWrapper và cấu trúc đối tượng | Có trong giới hạn accessor và cấu trúc đối tượng |
| Rủi ro làm mất bất biến do bỏ qua setter | Ít hơn nếu setter bảo vệ đúng, nhưng vẫn cần kiểm soát input | Cao hơn vì bypass setter |
| Dùng cho input HTTP không tin cậy | Chỉ với DTO chuyên dụng và giới hạn field | Không nên dùng theo cảnh báo của Spring |

**Điểm quan trọng:** lựa chọn BeanWrapper không làm dữ liệu tự động hợp lệ. Nếu setter không tồn tại, sai tên, chuyển đổi thất bại hoặc field bị chặn bởi allowlist, **bind(...)** có thể không thay đổi đối tượng. Cần quan sát **BindingResult** và những field bị suppress, chứ không chỉ quan sát các giá trị sau cùng.

## 4. Ví dụ chạy được với Java 17+: cùng input, kết quả khác nhau

Ví dụ này chủ động cung cấp dữ liệu trong mã nguồn, không nhận dữ liệu HTTP. Nó chứng minh setter được gọi ở chế độ JavaBeans, setter bị bỏ qua ở direct field mode, phép chuyển đổi **String → Integer**, và việc một allowlist chặn thuộc tính không được phép sửa.

Dùng **Spring Framework 7.0.10** (mốc phụ thuộc cố định để minh họa) với Java 17+. Chỉ thêm **spring-context** vì thư viện này kéo theo các module Spring cần thiết cho DataBinder. Khi triển khai ứng dụng thực, hãy dùng phiên bản phù hợp với bộ dependency của dự án và kiểm tra bản vá đang được hỗ trợ.

Cấu trúc:

~~~text
binder-access-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BinderAccessDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>binder-access-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.10</version>
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
                    <mainClass>demo.BinderAccessDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/BinderAccessDemo.java**:

~~~java
package demo;

import java.util.Arrays;
import java.util.Locale;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

public final class BinderAccessDemo {

    public static void main(String[] args) {
        Profile byProperty = new Profile();
        DataBinder beanBinder = new DataBinder(byProperty, "profile");
        beanBinder.initBeanPropertyAccess();
        beanBinder.setAllowedFields("displayName", "age");
        beanBinder.bind(inputValues());

        System.out.println("[BEAN PROPERTY]");
        print(byProperty, beanBinder);

        Profile byField = new Profile();
        DataBinder directBinder = new DataBinder(byField, "profile");
        directBinder.initDirectFieldAccess();
        directBinder.setAllowedFields("displayName", "age");
        directBinder.bind(inputValues());

        System.out.println("[DIRECT FIELD]");
        print(byField, directBinder);

        FieldOnly fieldOnly = new FieldOnly();
        DataBinder fieldOnlyBinder = new DataBinder(fieldOnly, "fieldOnly");
        fieldOnlyBinder.initDirectFieldAccess();
        fieldOnlyBinder.setAllowedFields("code");

        MutablePropertyValues codeValues = new MutablePropertyValues();
        codeValues.add("code", "X9");
        fieldOnlyBinder.bind(codeValues);
        System.out.println("fieldOnly.code='" + fieldOnly.code() + "'");
    }

    private static MutablePropertyValues inputValues() {
        MutablePropertyValues values = new MutablePropertyValues();
        values.add("displayName", "  Lan  ");
        values.add("age", "21");
        values.add("role", "admin");
        return values;
    }

    private static void print(Profile profile, DataBinder binder) {
        System.out.println("name='" + profile.getDisplayName() + "'");
        System.out.println("age=" + profile.getAge());
        System.out.println("role='" + profile.getRole() + "'");
        System.out.println("errors=" + binder.getBindingResult().getErrorCount());
        System.out.println("suppressed=" + Arrays.toString(
                binder.getBindingResult().getSuppressedFields()));
    }

    public static final class Profile {
        private String displayName;
        private Integer age;
        private String role = "viewer";

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String value) {
            this.displayName = value.strip().toUpperCase(Locale.ROOT);
        }

        public Integer getAge() {
            return age;
        }

        public void setAge(Integer age) {
            this.age = age;
        }

        public String getRole() {
            return role;
        }

        // Cố ý không có setRole(...).
    }

    public static final class FieldOnly {
        private String code = "INIT";

        public String code() {
            return code;
        }

        // Không có getCode()/setCode(...).
    }
}
~~~

Trong thư mục chứa **pom.xml**, chạy:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra chương trình dự kiến (không tính log Maven nếu môi trường tự bật logging):

~~~text
[BEAN PROPERTY]
name='LAN'
age=21
role='viewer'
errors=0
suppressed=[role]
[DIRECT FIELD]
name='  Lan  '
age=21
role='viewer'
errors=0
suppressed=[role]
fieldOnly.code='X9'
~~~

**Diễn giải kết quả:**

1. **BEAN PROPERTY:** input **"  Lan  "** đi vào **setDisplayName(...)**, nơi **strip()** bỏ khoảng trắng và **toUpperCase(Locale.ROOT)** tạo **"LAN"**. Chuỗi **"21"** được binder chuyển thành **Integer(21)** để đưa cho setter **setAge(Integer)**.
2. **DIRECT FIELD:** input vẫn là **"  Lan  "** trong field **displayName** vì Spring gán trực tiếp, không chạy **setDisplayName(...)**. Field **age** vẫn được chuyển thành Integer, chứng tỏ direct field access không có nghĩa là bỏ chuyển kiểu.
3. **Cả hai chế độ:** request mô phỏng chứa **role=admin**, nhưng **setAllowedFields("displayName", "age")** chỉ cho phép hai tên đã khai báo. Vì vậy **role** giữ **"viewer"** và được ghi trong danh sách **suppressed**. Lưu ý **suppressed** không tương đương **FieldError**; kết quả có thể cho **errors=0** dù một field bị từ chối bind.
4. **FieldOnly:** **code** là field private không có setter chuẩn JavaBeans. Trong tình huống nội bộ tin cậy, direct field mode có thể bind nó thành **"X9"**. Đừng dùng ví dụ này làm lý do cho phép khách HTTP sửa bất kỳ private field nào.

Với lớp Profile như trên, đổi **age** thành chuỗi **"abc"** sẽ dẫn tới lỗi chuyển kiểu khi cố gán cho **Integer**; kiểm tra **binder.getBindingResult().hasFieldErrors("age")** và loại **FieldError** để xử lý. Đây là kiểm thử bổ sung, không thuộc stdout cố định phía trên.

## 5. Khi nào chọn mỗi chế độ?

### 5.1. Trường hợp phù hợp cho bean property access

Chọn mặc định khi làm việc với:

- JavaBean có getter/setter rõ ràng.
- DTO đầu vào dùng setter để chuẩn hóa quy ước nội bộ, chẳng hạn viết hoa một mã hay trim theo chính sách đã xác định.
- Các cơ chế Spring thông thường dựa trên property path: property descriptors, nested properties, conversion và BindingResult.
- Controller Spring MVC nhận form bằng **@ModelAttribute**, với DTO chỉ gồm những trường khách được phép cập nhật.

**Không phải mọi setter đều đáng tin cậy.** Setter có thể ném exception, tạo hiệu ứng phụ hoặc tự ghi dữ liệu không hợp lệ. Validation vẫn phải chạy khi cần. Đặt logic nghiệp vụ quan trọng ở tầng thích hợp và tránh tin rằng chỉ cần getter/setter là đã chống được mass assignment.

### 5.2. Khi nào direct field access có thể hữu ích?

Đây là tùy chọn nâng cao khi code nội bộ kiểm soát được cả **nguồn giá trị** lẫn **kiểu target**. Ví dụ một công cụ chuyển đổi dữ liệu nội bộ cần đặt field vào một cấu trúc được thiết kế để thao tác bằng reflection và không có setter JavaBeans. Lúc đó phải xác định rõ:

- Field nào thực sự cần bind và vì sao không dùng constructor/setter.
- Ai tạo input, input có được kiểm soát hay không.
- Quy tắc bất biến nào sẽ bị bỏ qua nếu setter không chạy.
- Cách chọn allowlist, kiểm tra giá trị sau bind và tránh ghi vào field không được phép.
- Cách kiểm thử với class có private field, final field, nested object và giới hạn truy cập của Java module system.

**Cảnh báo an toàn bắt buộc:** Spring khuyến nghị không dùng direct field access khi bind nguồn không tin cậy. Với input web, ưu tiên DTO chuyên dụng hoặc constructor binding và giới hạn những thuộc tính cho phép. Kể cả có allowlist, không nên tùy tiện bật direct mode trên entity miền hay đối tượng chứa trạng thái nhạy cảm.

## 6. init phải gọi ở thời điểm nào?

Cách bố trí dễ hiểu nhất:

~~~java
Profile target = new Profile();
DataBinder binder = new DataBinder(target, "profile");

binder.initBeanPropertyAccess(); // Hoặc initDirectFieldAccess() cho nguồn tin cậy.
binder.setAllowedFields("displayName", "age");

// Tùy ứng dụng: cấu hình converter, formatter, editor, validator...
binder.bind(propertyValues);
BindingResult result = binder.getBindingResult();
~~~

Đoạn này minh họa, chưa độc lập: cần biến **propertyValues**, các import và lớp **Profile** phù hợp. Với bean property access, có thể bỏ dòng **initBeanPropertyAccess()** vì đó là chế độ mặc định.

**Không chọn chế độ sau khi binder đã sử dụng.** Ví dụ:

~~~java
DataBinder binder = new DataBinder(new Profile(), "profile");
binder.getBindingResult();  // Cơ chế truy cập nội bộ đã được khởi tạo.
binder.initDirectFieldAccess(); // IllegalStateException.
~~~

Ví dụ này minh họa trường hợp thất bại; không chạy như một phần của chương trình ở mục 4. Spring kiểm tra trạng thái đã khởi tạo và từ chối việc đổi chế độ khi BindingResult nội bộ đã được tạo. Không thiết kế mã để liên tục chuyển qua lại giữa hai chế độ trên cùng một binder; hãy dùng hai binder độc lập như ví dụ.

Cũng không nên trông chờ **initBeanPropertyAccess()** có tác dụng “reset” target hay xóa lỗi trước đó. Hai phương thức này chọn chiến lược truy cập, không thực hiện lại phép bind, không chạy validator và không xóa BindingResult.

## 7. Mối quan hệ với BeanWrapper, DataBinder và BindingResult

Để định vị đúng trách nhiệm:

| Thành phần | Chịu trách nhiệm chính | Quan hệ với chế độ access |
| --- | --- | --- |
| **BeanWrapper / BeanWrapperImpl** | Đọc/ghi thuộc tính JavaBeans, kể cả đường dẫn thuộc tính lồng nhau | Được dùng trong chế độ bean property |
| **DirectFieldAccessor** | Đọc/ghi field bằng reflection | Được dùng trong chế độ direct field |
| **DataBinder** | Điều phối việc nhận PropertyValues, giới hạn field, chuyển kiểu, ghi dữ liệu, tùy chọn validation | Chọn chiến lược bằng hai phương thức init |
| **BeanPropertyBindingResult** | Lưu lỗi và truy cập thông tin binding theo property | Dành cho chế độ bean property |
| **DirectFieldBindingResult** | Lưu lỗi và truy cập thông tin binding theo field | Dành cho chế độ direct field |
| **ConversionService / PropertyEditor** | Chuyển giá trị đầu vào sang kiểu Java đích khi cần | Có thể tham gia ở cả hai chế độ |
| **Validator / @Valid** | Kiểm tra các ràng buộc trên đối tượng đã được bind | Tách biệt với lựa chọn cách ghi giá trị |

**Chọn cách truy cập khác với chọn cách xác thực.** Cùng một validator có thể đánh giá target sau khi bind ở cả hai chế độ, nhưng kết quả có thể khác vì setter của chế độ bean đã thay đổi dữ liệu còn direct mode bỏ qua setter.

**Một lỗi conversion không tự biến mất vì đổi sang direct mode.** Nếu field có kiểu **Integer**, dữ liệu **"abc"** vẫn không có cách chuyển hợp lệ chỉ vì binder đang dùng reflection. Kiểm tra **BindingResult**; nếu muốn kiểm tra annotation như **@Min** hoặc **@NotBlank**, bảo đảm validation được cấu hình/kích hoạt riêng.

**Auto-grow nested paths** không phải lối tắt an toàn để ghi vào bất kỳ đối tượng lồng nhau nào. Đường dẫn thuộc tính có thể tạo thêm object/collection theo các giới hạn và cấu hình của binder. Với nguồn không tin cậy, cần giới hạn rõ các property path và kích thước cấu trúc, không tăng hạn mức chỉ để “bind cho thành công”.

## 8. Liên hệ với Spring MVC và annotation

Khi một Spring MVC controller nhận form bằng **@ModelAttribute**, Spring thường tạo **WebDataBinder** để gán dữ liệu vào DTO. **WebDataBinder** là lớp con của DataBinder nên kế thừa hai phương thức init. Một cấu hình binder minh họa:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

// Đặt trong @Controller/@ControllerAdvice của ứng dụng Spring MVC:
@InitBinder("profile")
public void configureProfileBinder(WebDataBinder binder) {
    binder.initBeanPropertyAccess();  // Mặc định; ghi rõ cho dễ đọc.
    binder.setAllowedFields("displayName", "age");
}
~~~

Đây là **đoạn cấu hình tích hợp**, không phải ứng dụng độc lập. Tên **profile** phải khớp đối tượng cần cấu hình. Trên WebDataBinder, các cấu hình có thể được thực hiện trước quá trình bind; việc gọi init sau khi binding result đã được tạo sẽ không hợp lệ.

**Không chuyển sang initDirectFieldAccess() trong controller nhận dữ liệu HTTP để “khắc phục thiếu setter”.** Đây là dữ liệu không tin cậy, còn truy cập field trực tiếp có thể bỏ qua các ranh giới API của đối tượng. Nếu DTO thiếu setter, xem xét thiết kế DTO đầu vào riêng, constructor binding/record phù hợp hoặc chỉnh lại hợp đồng đầu vào.

**@RequestBody** đi theo cơ chế khác: HTTP body được đọc bởi **HttpMessageConverter** (thường dùng Jackson cho JSON), vì vậy các phương thức init của DataBinder **không phải công tắc bắt Jackson chuyển từ setter sang direct field**. Không kết luận rằng gọi **@InitBinder** sẽ thay đổi cách Jackson giải tuần tự JSON.

**Constructor binding** là một cơ chế riêng: Spring có thể dựng target từ đối số constructor trước khi property binding xảy ra. Hai init method trong bài quyết định cách truy cập khi bind giá trị vào thuộc tính/field của target; chúng không phải annotation chuyển kiểu hay cấu hình giải tuần tự JSON.

## 9. Lỗi phổ biến và cách chẩn đoán

1. **“Dùng initBeanPropertyAccess() mới bật được DataBinder”.** Sai: JavaBeans access đã là mặc định. Gọi rõ có thể làm ý đồ dễ hiểu hơn, không phải điều kiện để DataBinder hoạt động.
2. **“Field private thì DataBinder không thể bind trong mọi trường hợp”.** Sai: direct field access có thể chạm field private khi reflection cho phép. Chính vì vậy phải coi đây là quyền mạnh và giới hạn phạm vi sử dụng.
3. **“Direct field access cũng chạy setter”.** Sai: setter bị bỏ qua. Những bước chuẩn hóa, logging hoặc điều kiện nằm trong setter sẽ không được thực hiện qua đường này.
4. **“Direct mode không cần converter”.** Sai: giá trị đầu vào vẫn phải phù hợp kiểu Java của field.
5. **“Chuyển chế độ sau khi bind để thử lại được”.** Sai: một khi internal BindingResult đã được tạo, việc gọi init lại bị từ chối; tạo binder mới nếu muốn thực nghiệm.
6. **“Không có FieldError là mọi giá trị đã bind”.** Sai: một input có thể bị suppress bởi **setAllowedFields**. Kiểm tra cả **getSuppressedFields()** và trạng thái target.
7. **“Có setter nghĩa là mọi input có thể sửa nó”.** Sai: allowlist, hợp đồng DTO và các kiểm tra khác vẫn quyết định field nào được phép cập nhật.
8. **“Chỉ cần chuyển qua direct để bind entity JPA từ request”.** Nguy hiểm: entity có thể chứa field và quan hệ không được thiết kế cho khách sửa. Ưu tiên DTO đầu vào hẹp và ánh xạ theo quy tắc nghiệp vụ.
9. **“@Valid quyết định dùng BeanWrapper hay reflection”.** Sai: validation và phương thức truy cập là hai việc độc lập.
10. **“@RequestBody JSON chắc chắn tuân theo initDirectFieldAccess”.** Sai: Jackson xử lý JSON thông qua message converter; cần cấu hình riêng đúng lớp chịu trách nhiệm.

Khi gặp lỗi, hãy kiểm tra theo thứ tự: tên property/field; target có setter hợp lệ hay field có thể ghi; binder đang ở chế độ nào; allowlist; kiểu đích và converter; BindingResult/binding failures; cuối cùng là validation riêng. Cách này chỉ ra nguyên nhân cụ thể thay vì tắt kiểm soát truy cập.

## 10. Bài tập thực hành

**Bài tập A — Setter có tác dụng phụ.** Trong ví dụ, sửa **setDisplayName(...)** để thêm một bộ đếm số lần gọi setter. Dự đoán số lần ở bean mode và direct mode, rồi chạy để xác minh. Giải thích vì sao đặt nghiệp vụ quan trọng chỉ trong setter không đáng tin nếu đối tượng còn có đường ghi field trực tiếp khác.

**Bài tập B — Trường không có setter.** Tạo một class chỉ có private field **serialNumber**, thêm phương thức chỉ đọc để xem giá trị. So sánh khả năng gán qua DataBinder mặc định và direct mode trên dữ liệu **do test tạo ra**. Chỉ rõ vì sao không nên đem cấu hình direct vào endpoint nhận dữ liệu tùy ý của người dùng.

**Bài tập C — Conversion và lỗi.** Đổi input **age** từ **"21"** sang **"bad"** trong cả hai chế độ. Quan sát **hasFieldErrors("age")**, danh sách **FieldError** và giá trị target. Chỉ thay chế độ access có làm **"bad"** thành Integer được không?

**Bài tập D — Cấu hình sớm.** Tạo binder rồi gọi **getBindingResult()** trước **initDirectFieldAccess()**. Dự đoán loại ngoại lệ và mô tả vì sao quy tắc chọn chế độ phải thực hiện trước thao tác khởi tạo nội bộ.

**Bài tập E — Đầu vào bên ngoài.** Giả sử DTO có **role**, **active**, **balance** và **email**. Thiết kế DTO cho yêu cầu cập nhật email: chỉ trường nào được phép có trong hợp đồng? Có nên bind trực tiếp entity bằng direct field access không? Nêu cách giới hạn thuộc tính và nơi kiểm tra quyền cập nhật.

## 11. Tài liệu chính thức

- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): JavaBeans property access, BeanWrapper và mối liên hệ với DataBinder.
- [DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DataBinder.html): initBeanPropertyAccess(), initDirectFieldAccess(), setAllowedFields(), bind() và BindingResult.
- [BeanWrapper Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/BeanWrapper.html): thuộc tính có thể đọc/ghi và nested properties.
- [DirectFieldAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/DirectFieldAccessor.html): truy cập field trực tiếp.
- [Spring Web MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): cấu hình binder trong controller với @InitBinder.

**Điểm cần nhớ:** DataBinder mặc định gán dữ liệu qua JavaBeans và setter. **initDirectFieldAccess()** chuyển sang truy cập field bằng reflection, làm thay đổi những logic có thể chạy trong setter và mở rộng khả năng ghi dữ liệu trong đối tượng. Chọn chế độ trước khi bind, kiểm tra kết quả bằng BindingResult, và chỉ cân nhắc direct field access với nguồn dữ liệu tin cậy được kiểm soát.