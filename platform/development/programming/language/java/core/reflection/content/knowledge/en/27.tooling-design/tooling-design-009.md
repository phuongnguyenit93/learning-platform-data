# JavaBeans Introspector và khác biệt với duyệt field trực tiếp

## 1. Vì sao công cụ Java cần phân biệt property và field?

`Field` biểu diễn biến lưu trữ thật; **JavaBeans property** biểu diễn một hợp đồng logic được phát hiện chủ yếu từ getter/setter. `getSummary()` có thể công bố một property tính toán mà không có field `summary`, còn `internalCache` có thể là field thật nhưng không có property. Dùng `getDeclaredFields()` để mô phỏng JavaBeans sẽ làm sai schema.

Khác với bài về **lựa chọn chiến lược field/property/accessor**, bài này đi sâu vào JDK `java.beans.Introspector`, `BeanInfo`, `PropertyDescriptor`: quy tắc `getX`/`isX`/`setX`, kế thừa, custom BeanInfo, read/write method và giới hạn truy cập. Trong named module, `java.beans` thuộc module `java.desktop`; mã modular cần quan hệ đọc phù hợp.

## 2. JavaBeans property được suy ra thế nào?

Các mẫu cơ bản:

| Phương thức public | Property được nhận diện | Vai trò |
| --- | --- | --- |
| **String getName()** | **name** | Getter của property **name** |
| **void setName(String value)** | **name** | Setter của property **name** |
| **boolean isActive()** | **active** | Getter boolean theo dạng **isX** |
| **int getCount()** | **count** | Getter với kiểu primitive |
| **String getSummary()** | **summary** | Read-only property nếu không có setter tương ứng |
| **void setPassword(String value)** | **password** | Write-only property nếu không có getter tương ứng |
| **String name()** | Không tự nhận thành property **name** bằng quy ước getter JavaBeans truyền thống | Method bình thường; thường gặp ở record |
| **public String raw;** | Không tự nhận thành property **raw** chỉ vì có field | Field công khai không phải getter/setter |

Một property có thể là:
- **Read-write**: getter và setter tương thích.
- **Read-only**: có getter nhưng thiếu setter.
- **Write-only**: có setter nhưng thiếu getter.
- **Computed/derived**: getter tính giá trị từ dữ liệu khác, không cần field cùng tên.
- **Inherited**: getter hoặc setter công khai được thừa kế từ lớp cha.

Những quy ước quen thuộc là getter không có tham số và trả một giá trị; setter có một tham số, trả **void** theo JavaBeans convention. Với getter dạng **isX()**, loại trả về kiểu **boolean nguyên thủy** là quy tắc an toàn; đừng giả định mọi công cụ sẽ chấp nhận **Boolean** hoặc signature không chuẩn như nhau. Với các overload getter/setter phức tạp, kiểu property được suy ra có thể không như dự kiến; cần kiểm tra kết quả **PropertyDescriptor** thực tế.

Tên property dùng quy tắc **Introspector.decapitalize**:
- **getName()** → **name**.
- **getURL()** → **URL**, vì hai ký tự đầu của phần “URL” đều viết hoa.
- **getEMail()** → **EMail**, không phải luôn **eMail**.
- **getX()** → **x**.

Việc đặt tên method theo convention là điều kiện quan trọng khi viết bean để thư viện khác có thể khám phá một cách nhất quán.

## 3. API chính: Introspector, BeanInfo, PropertyDescriptor

### 3.1. Lấy thông tin JavaBeans

Cách sử dụng đơn giản:

~~~java
BeanInfo info = Introspector.getBeanInfo(Person.class);
PropertyDescriptor[] properties = info.getPropertyDescriptors();
~~~

Hai câu lệnh trên là **đoạn minh họa**, cần import **java.beans.BeanInfo**, **java.beans.Introspector**, **java.beans.PropertyDescriptor** và có class **Person** thật.

Những thành phần quan trọng:

| API | Nhiệm vụ |
| --- | --- |
| **Introspector.getBeanInfo(Class<?>)** | Khám phá BeanInfo của class và hệ kế thừa theo cơ chế JavaBeans |
| **Introspector.getBeanInfo(Class<?>, Class<?> stopClass)** | Bỏ qua thông tin từ **stopClass** và các lớp cha của nó |
| **Introspector.getBeanInfo(Class<?>, Class<?> stopClass, int flags)** | Thêm tùy chọn dùng/bỏ qua lớp BeanInfo cung cấp tường minh |
| **BeanInfo.getPropertyDescriptors()** | Danh sách các property descriptor |
| **PropertyDescriptor.getName()** | Tên property logic |
| **PropertyDescriptor.getPropertyType()** | Kiểu của property thông thường |
| **PropertyDescriptor.getReadMethod()** | Getter **Method**, có thể **null** |
| **PropertyDescriptor.getWriteMethod()** | Setter **Method**, có thể **null** |
| **BeanInfo.getMethodDescriptors()** | Metadata method liên quan đến JavaBean |
| **BeanInfo.getEventSetDescriptors()** | Metadata sự kiện theo JavaBeans event convention |

**getBeanInfo(Person.class)** thường có thể bao gồm property **class**, vì public **Object.getClass()** trông giống một getter. Khi công cụ chỉ cần property nghiệp vụ, dùng:

~~~java
BeanInfo info = Introspector.getBeanInfo(
        Person.class,
        Object.class,
        Introspector.IGNORE_ALL_BEANINFO);
~~~

**Object.class** là điểm dừng: không đưa property/method/event thuộc Object và các lớp phía trên vào kết quả. Cờ **IGNORE_ALL_BEANINFO** bảo Introspector bỏ qua các BeanInfo tường minh có thể có trong class hoặc lớp cha; điều này làm ví dụ học quy ước getter/setter dễ dự đoán hơn. Trong công cụ sản xuất, bạn **không nên mặc định bỏ qua BeanInfo tường minh** nếu sản phẩm muốn tôn trọng cấu hình metadata do tác giả bean cung cấp.

**JavaBeans là metadata ở mức public API.** Lấy descriptor không tự động trao quyền gọi private method hoặc truy cập private field.

### 3.2. Lớp BeanInfo tường minh và bộ nhớ đệm

Ngoài suy luận theo tên method, JavaBeans cho phép tác giả cung cấp metadata **BeanInfo** tường minh, thường là class tên **FooBeanInfo** đi cùng **Foo**. Metadata này có thể điều chỉnh những property được xuất ra cho các công cụ. Chính vì vậy, kết quả introspection không nhất thiết chỉ là kết quả áp quy tắc tên getter/setter cơ học.

**Introspector** có cache để giảm chi phí phân tích lại. API **flushFromCaches(Class<?>)** hoặc **flushCaches()** phục vụ trường hợp cần xóa dữ liệu đã cache có chủ đích. Đừng xóa toàn bộ cache ở mỗi lần inspect; hãy dùng cache của JDK bình thường và tránh introspection quá thường xuyên trên đường chạy nóng.

## 4. Duyệt field trực tiếp bằng Reflection khác gì?

Với class **Person**, Reflection có các họ API:

| Reflection API | Trả về | Quy tắc |
| --- | --- | --- |
| **getDeclaredFields()** | Field được khai báo trực tiếp trên class, gồm cả private | Không tự thêm field chỉ kế thừa từ lớp cha |
| **getFields()** | Các field **public** có thể truy cập theo quy tắc kế thừa | Không liệt kê toàn bộ private field |
| **getDeclaredField("name")** | Một field khai báo trực tiếp có tên chính xác | Nếu không tồn tại sẽ ném **NoSuchFieldException** |
| **Field.getType()** | Kiểu runtime thô của field | Với generic, có thể cần **getGenericType()** |
| **Field.get(obj)** | Giá trị field khi có quyền truy cập | Không gọi getter JavaBeans |
| **Field.set(obj, value)** | Thử gán field theo quyền và quy tắc Reflection | Không gọi setter/validation nghiệp vụ của bean |

Vì vậy:

- Một field **private String internalCode** xuất hiện trong **getDeclaredFields()**, nhưng chưa chắc là JavaBeans property.
- Một method **getSummary()** tính chuỗi từ các dữ liệu khác có thể tạo property **summary**, dù class không có field **summary**.
- Field **public String raw** hiển thị trong Reflection field scan, nhưng sẽ không tự tạo JavaBeans property **raw** nếu không có accessor phù hợp.
- Property **id** do getter từ lớp cha có thể xuất hiện qua Introspector, trong khi **getDeclaredFields()** của lớp con không chứa field **id**.
- Hai API đều cần xử lý thứ tự sắp xếp tường minh nếu muốn báo cáo cố định; không coi thứ tự field trả về là thứ tự viết trong source đã được bảo đảm.

**Không đánh đồng quyền nhìn thấy metadata với quyền sử dụng:** **getDeclaredFields()** có thể mô tả private field, nhưng gọi **Field.get** hoặc **Field.set** vẫn chịu kiểm tra truy cập và Java module encapsulation. **setAccessible(true)** có thể bị từ chối; đây không phải cách mặc định để xây một công cụ JavaBeans inspector.

## 5. Ví dụ Java 17+ chạy được: cùng class, hai cách nhìn

Lưu mã sau vào **BeanVsFieldDemo.java**. Đây là chương trình độc lập, dùng API JDK và không cần thư viện bên ngoài.

~~~java
import java.beans.BeanInfo;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public class BeanVsFieldDemo {
    public static class Base {
        private final String id;

        public Base(String id) {
            this.id = id;
        }

        public String getId() {
            return id;
        }
    }

    public static class Profile extends Base {
        public String raw = "raw-only";
        private String displayName = "Lan";
        private boolean active = true;
        private String internalCode = "hidden";

        public Profile() {
            super("P-1");
        }

        public String getDisplayName() {
            return displayName;
        }

        public void setDisplayName(String displayName) {
            this.displayName = displayName;
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }

        public String getSummary() {
            return displayName + " (" + getId() + ")";
        }
    }

    public static void main(String[] args) throws Exception {
        // 1. Lấy field được khai báo trực tiếp trong Profile.
        Field[] fields = Profile.class.getDeclaredFields();
        Arrays.sort(fields, Comparator.comparing(Field::getName));
        System.out.println("FIELDS: " + String.join(", ",
                Arrays.stream(fields).map(Field::getName).toList()));

        // 2. Khám phá property theo getter/setter, lấy cả kế thừa.
        BeanInfo beanInfo = Introspector.getBeanInfo(
                Profile.class,
                Object.class,
                Introspector.IGNORE_ALL_BEANINFO);

        PropertyDescriptor[] props = beanInfo.getPropertyDescriptors();
        Arrays.sort(props, Comparator.comparing(PropertyDescriptor::getName));

        System.out.println("PROPERTIES: " + String.join(", ",
                Arrays.stream(props).map(PropertyDescriptor::getName).toList()));

        for (PropertyDescriptor p : props) {
            System.out.println(p.getName() + ": read="
                    + (p.getReadMethod() == null
                        ? "-" : p.getReadMethod().getName())
                    + ", write="
                    + (p.getWriteMethod() == null
                        ? "-" : p.getWriteMethod().getName()));
        }

        // 3. Ghi property qua setter, đọc computed property qua getter.
        Profile profile = new Profile();

        for (PropertyDescriptor p : props) {
            if (p.getName().equals("displayName")) {
                p.getWriteMethod().invoke(profile, "Mai");
            }
            if (p.getName().equals("summary")) {
                System.out.println(
                        "summary=" + p.getReadMethod().invoke(profile));
            }
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 BeanVsFieldDemo.java
java BeanVsFieldDemo
~~~

Đầu ra kiểm chứng với JDK 17+:

~~~text
FIELDS: active, displayName, internalCode, raw
PROPERTIES: active, displayName, id, summary
active: read=isActive, write=setActive
displayName: read=getDisplayName, write=setDisplayName
id: read=getId, write=-
summary: read=getSummary, write=-
summary=Mai (P-1)
~~~

**Giải thích điều quan trọng nhất:**

1. **getDeclaredFields()** thấy bốn field **active**, **displayName**, **internalCode**, **raw** trên **Profile**, dù private hay public. Field **id** được khai báo trong **Base**, nên không nằm trong kết quả này.
2. **Introspector** nhận **active** từ **isActive/setActive**, nhận **displayName** từ **getDisplayName/setDisplayName**.
3. **id** là property kế thừa qua **Base.getId()**, không cần **Profile** có field **id**.
4. **summary** là property chỉ đọc từ **getSummary()**, **không có field summary**; kết quả phụ thuộc trạng thái hiện tại của object.
5. **internalCode** là field private không có getter/setter; **raw** là field public không có accessor. Cả hai **không trở thành property** theo convention.
6. **PropertyDescriptor.getReadMethod/getWriteMethod** có thể trả về **null**. Ví dụ **id** và **summary** không có setter nên in dấu **-**.
7. **setDisplayName("Mai")** được gọi qua **Method.invoke**; sau đó getter **getSummary()** tạo ra chuỗi **Mai (P-1)**. Ví dụ không cần truy cập private field.

**Giới hạn của ví dụ:** chỉ thao tác với property đã xác định và các method public. Trong công cụ xử lý input thực, cần xác minh loại property, quyền cho phép, khả năng write, kiểu dữ liệu và nguy cơ side effect trước khi gọi setter.

## 6. Chọn Introspector hay Field Reflection cho từng mục đích

| Bài toán | Nên bắt đầu bằng | Lý do |
| --- | --- | --- |
| Hiển thị biểu mẫu chỉnh sửa thông qua API công khai của bean | **PropertyDescriptor** | Biết property nào đọc/ghi được bằng getter/setter |
| Công cụ phát hiện property kế thừa | **Introspector** | Nhận getter/setter public ở hệ lớp cha theo quy tắc JavaBeans |
| Kiểm tra cấu trúc field trong class hiện tại | **getDeclaredFields()** | Có metadata về field kể cả private |
| Đọc annotation đặt trực tiếp lên field | **Field.getDeclaredAnnotations()** | Chú thích có thể gắn ở field, không ở getter |
| Đọc annotation trên getter | **PropertyDescriptor.getReadMethod()** rồi kiểm tra method | Annotation ở getter không tự xuất hiện trên Field |
| Mapping qua các setter công khai có kiểm tra nghiệp vụ | **Introspector** và gọi setter có kiểm soát | Cho phép logic trong setter chạy; cần xét side effect |
| Công cụ debug/trình kiểm tra cấp thấp đối tượng | **Reflection Field**, chỉ khi thật sự cần | Có thể phân tích trạng thái vật lý không được public API cung cấp |
| Lấy dữ liệu computed như **summary** | **Introspector** | Không cần có field tên **summary** |

Một công cụ có thể dùng **cả hai cách** nếu mỗi nguồn metadata có ý nghĩa riêng, nhưng cần chỉ rõ đang hiển thị **field vật lý**, **property logic** hay hai danh sách tương ứng. Ghép chúng theo tên rồi xem là đồng nhất dễ làm mất hoặc gán nhầm thông tin.

### Những trường hợp không nên dùng quy tắc tên như bộ suy đoán tuyệt đối

- Java record thường có accessor kiểu **name()** thay vì **getName()**; JavaBeans Introspector tiêu chuẩn không nên được giả định tự coi mọi accessor của record là property JavaBeans.
- API fluent như **Person name(String value)** hoặc **Person withName(...)** không theo setter **void setName(...)** truyền thống; các framework hiện đại có thể hỗ trợ quy ước mở rộng riêng.
- Getter có thể trả kết quả tính toán, gọi database hoặc ném lỗi. **Thấy getter** không đồng nghĩa **gọi getter luôn rẻ và an toàn**.
- Cùng tên property có thể xuất hiện từ nhiều method overload hoặc kế thừa; thay vì tự ghép chuỗi method, nên lấy **PropertyDescriptor** thực tế và ghi nhận lựa chọn của Introspector.

## 7. Lọc property và đọc/ghi an toàn

Một quy trình phù hợp cho công cụ cấu hình hoặc inspector:

1. Gọi **Introspector.getBeanInfo(type, Object.class)** để tránh property **class** của Object nếu không cần.
2. Lấy **PropertyDescriptor[]** và sắp xếp theo tên nếu muốn kết quả ổn định.
3. Lọc property theo **allowlist** rõ ràng; không tự động gọi getter/setter cho mọi property tìm được.
4. Với thao tác đọc, kiểm tra **getReadMethod() != null**; với thao tác ghi, kiểm tra **getWriteMethod() != null**.
5. Trước khi ghi, kiểm tra **getPropertyType()**, kiểu input, tính tương thích, quy tắc validation và quyền của caller.
6. Bắt và phân loại lỗi thao tác như **IllegalAccessException**, **InvocationTargetException**, **IllegalArgumentException**; nếu dùng **Method.invoke**, ngoại lệ do getter/setter ném thường nằm trong **InvocationTargetException.getCause()**.
7. Ghi log thông tin đủ để chẩn đoán nhưng tránh lộ nội dung nhạy cảm từ các property như password, token, secret.

Ví dụ lọc property theo tên:

~~~java
for (PropertyDescriptor p : info.getPropertyDescriptors()) {
    if (!p.getName().equals("displayName")) {
        continue;
    }
    if (p.getWriteMethod() == null) {
        throw new IllegalStateException("Property is read-only");
    }
    // Chỉ gọi setter sau khi đã xác minh object, input và quyền.
}
~~~

Đây là **đoạn minh họa**, giả sử biến **info** là **BeanInfo** đã thu được. Trong hệ thống thực, không nên lấy tên property tùy ý từ request rồi cho phép ghi trên mọi object: đó có thể là đường đi sửa trạng thái không mong muốn.

**Lưu ý về side effect:** gọi một getter JavaBeans qua Reflection là *thực thi code*. Nó có thể tải dữ liệu, sửa cache, thực hiện logic nghiệp vụ hoặc ném exception. Trái lại, chỉ lấy **PropertyDescriptor** để đọc tên/getter metadata về cơ bản là bước khám phá, chưa chủ động gọi getter của bean.

## 8. Những lỗi phổ biến khi làm công cụ introspection

### Nhầm field với property

Một class có field **private String name** nhưng không có getter/setter không bảo đảm Introspector trả property **name**. Ngược lại, một property có thể tồn tại mà không có field trùng tên. Cách sửa là xác định rõ công cụ cần **biểu diễn trạng thái nội bộ** hay **giao diện property**.

### Quên loại property class

**Object.getClass()** phù hợp hình thức getter, vì thế khi gọi **getBeanInfo(SomeClass.class)** bạn có thể thấy property **class**. Nếu không muốn nó trong biểu mẫu nghiệp vụ, sử dụng overload với **stopClass=Object.class** hoặc lọc cẩn thận; không xem nó là field người dùng cần chỉnh.

### Gọi setter khi write method bằng null

Read-only property như **summary** không có setter. **getWriteMethod()** trả **null**, nên gọi **invoke** không kiểm tra gây **NullPointerException**. Tương tự, write-only property có thể không có getter.

### Dựa vào thứ tự mặc định

API liệt kê field, method và property không nên được sử dụng như hợp đồng thứ tự xuất ra trong tài liệu/JSON. Dùng **Comparator.comparing(PropertyDescriptor::getName)** hoặc tiêu chí xác định riêng.

### Quên kế thừa hoặc coi JavaBeans chỉ dựa trên field

**getDeclaredFields()** không đưa field của Base vào, trong khi Introspector vẫn có thể thấy getter thừa kế. Nếu dùng **getFields()**, kết quả chỉ có field public được kế thừa/khai báo theo quy tắc Reflection, vẫn không tương đương property.

### Bỏ qua BeanInfo tường minh

**Introspector** có thể sử dụng **FooBeanInfo** nếu lớp cung cấp metadata. **IGNORE_ALL_BEANINFO** chỉ phù hợp nếu bạn chủ động muốn suy luận theo convention và bỏ thông tin đó. Khi tích hợp công cụ hỗ trợ JavaBeans đầy đủ, hãy tôn trọng hợp đồng BeanInfo của thư viện.

### Dùng setAccessible để vượt qua encapsulation

Nếu mục tiêu là gọi getter/setter công khai, việc truy cập trực tiếp private field thường làm mất validation và phá hợp đồng public. Trong Java module system, **setAccessible(true)** còn có thể thất bại với **InaccessibleObjectException**. Ưu tiên API đúng mục đích.

### Quên module java.desktop

**java.beans** thuộc module **java.desktop**. Ở ứng dụng classpath thông thường trên JDK đầy đủ, API có thể dùng bằng import bình thường. Với **named module** có **module-info.java**, cần khai báo phụ thuộc:

~~~java
module com.example.inspector {
    requires java.desktop;
}
~~~

Đoạn trên chỉ minh họa cấu hình module; đặt tên module/package theo dự án thực tế.

## 9. Bài tập thực hành

**Bài tập 1 — Field và property không trùng tên.** Thêm **private String token** vào **Profile**, không thêm accessor. Dự đoán: **getDeclaredFields()** sẽ thấy **token**, nhưng **Introspector** không có property **token** chỉ vì field đó tồn tại.

**Bài tập 2 — Computed property.** Thêm getter **getGreeting()** trả về chuỗi dựa trên **displayName**; không khai báo field **greeting**. Chạy lại inspector: danh sách property có **greeting**, còn danh sách field không có tên đó.

**Bài tập 3 — Read-only vs write-only.** Thêm **setApiKey(String)** nhưng không có **getApiKey()**. Kiểm tra **PropertyDescriptor** thực tế, kết quả **getReadMethod()** và **getWriteMethod()**. Không in hoặc ghi lại bí mật trong bài thực hành.

**Bài tập 4 — Kế thừa.** Thêm getter **getCode()** ở **Base**; so sánh **Profile.class.getDeclaredFields()**, **Profile.class.getFields()** và Introspector trên **Profile** để giải thích khi nào kết quả gồm thành viên kế thừa.

**Bài tập 5 — Tên viết hoa.** Tạo **getURL()**, **setURL(String)** rồi chạy **Introspector.decapitalize("URL")** và kiểm tra tên property. Giải thích vì sao không nên tự viết thuật toán luôn đổi ký tự đầu thành chữ thường.

**Bài tập 6 — Phân biệt method và field annotation.** Gắn một annotation runtime lên field, một annotation lên getter tương ứng. Truy vấn annotation qua **Field** và qua **PropertyDescriptor.getReadMethod()**. Chứng minh chúng là hai vị trí metadata khác nhau.

## 10. Tự kiểm tra và kết luận kỹ thuật

**Câu 1.** Có **private String name** nhưng không có getter/setter. Introspector chắc chắn liệt kê property **name** không?  
**Đáp án:** Không. Field nội bộ không tự tạo property theo JavaBeans convention.

**Câu 2.** Không có field **fullName**, nhưng có **getFullName()** public đúng signature. Introspector có thể trả property **fullName** không?  
**Đáp án:** Có, đó có thể là computed read-only property.

**Câu 3.** Vì sao **getDeclaredFields()** của lớp con không đủ để biết toàn bộ property?  
**Đáp án:** Nó chỉ quét field khai báo trực tiếp, trong khi JavaBeans property đến từ getter/setter và có thể được kế thừa.

**Câu 4.** Khi nào **getWriteMethod()** trả null?  
**Đáp án:** Khi property descriptor không có setter được nhận diện. Công cụ phải xem nó là read-only trong ngữ cảnh đó.

**Câu 5.** Getter public có bảo đảm không gây side effect không?  
**Đáp án:** Không. Nó là code bình thường, chỉ khác ở tên và signature theo convention.

**Câu 6.** Vì sao có thể cần **getBeanInfo(type, Object.class)**?  
**Đáp án:** Để bỏ phần metadata từ **Object**, đặc biệt property **class** do **getClass()**.

**Câu 7.** Property trong JavaBeans và Spring bean có phải cùng khái niệm?  
**Đáp án:** Không. Property mô tả interface đọc/ghi của object; Spring bean là đối tượng được container quản lý.

**Tiêu chí hoàn thành:** bạn giải thích được output chương trình mẫu, chủ động chọn **PropertyDescriptor** hoặc **Field**, kiểm tra getter/setter null, xử lý tên property và kế thừa chính xác, biết giới hạn quyền truy cập và side effect khi triển khai inspector thật.

**Tài liệu tham khảo chính thức:** Oracle Java SE 21 API — **java.beans.Introspector**, **BeanInfo**, **PropertyDescriptor**, **java.lang.reflect.Field**, **java.lang.reflect.Method** và *JavaBeans Specification*.