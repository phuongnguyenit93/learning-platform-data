# Accessor của record và sự khác biệt với getter JavaBeans trong Java

> **Module:** Java Core — Class/Object  
> **Nhóm kiến thức:** Record  
> **Chủ đề trực tiếp:** Accessor của record và sự khác biệt với getter JavaBeans  
> **Phiên bản:** Java 17+ — record là một tính năng chuẩn kể từ Java 16.

## 1. Tóm tắt nhanh

Với một Java record:

~~~java
record Person(String name, int age, boolean active) {
}
~~~

Java cung cấp các **record component accessor methods**:

~~~java
Person person = new Person("Lan", 22, true);

System.out.println(person.name());    // Lan
System.out.println(person.age());     // 22
System.out.println(person.active());  // true
~~~

Tên accessor **trùng đúng tên component**, không tự thêm tiền tố `get` hoặc `is`:

| Record component | Accessor do record cung cấp | Getter kiểu JavaBeans thường gặp |
| --- | --- | --- |
| `String name` | `name()` | `getName()` |
| `int age` | `age()` | `getAge()` |
| `boolean active` | `active()` | `isActive()` hoặc `getActive()` |
| `Boolean verified` | `verified()` | Thường `getVerified()` |
| `List<String> tags` | `tags()` | `getTags()` |

**Các accessor `name()`, `age()` và `active()` là public instance methods do record khai báo ngầm nếu bạn không tự định nghĩa chúng.** Chúng trả giá trị của component field tương ứng theo record semantics. Không cần viết getter bằng tay cho các trường hợp cơ bản.

Đây là khác biệt chính:

- **Record accessor** là phần **contract của ngôn ngữ Java dành cho record components**.
- **JavaBeans getter** là **quy ước đặt tên phương thức** trên Java objects: `getX()` hoặc `isX()` cho thuộc tính boolean theo quy tắc JavaBeans. Nó không được Java compiler tự sinh cho mỗi record component.
- Một record có thể **bổ sung methods `getName()`/`isActive()`** để tương thích thư viện dựa trên JavaBeans, nhưng đó là các methods thêm, không thay thế component accessors bắt buộc.
- Một JavaBeans getter có thể biểu diễn thuộc tính tính toán hoặc một property không có field cùng tên; record component accessor gắn chặt với component declaration và có quy tắc chữ ký riêng.

Hiểu khác biệt này sẽ giúp bạn gọi đúng methods, thiết kế DTO, dùng method references, tích hợp JSON/ORM/UI frameworks, viết reflection code và bảo vệ dữ liệu mutable nằm bên trong record.

## 2. Record là gì trước khi nói về accessor?

Một record declaration:

~~~java
record Point(int x, int y) {
}
~~~

khai báo một **record class** có hai components `x` và `y`.

Trong Java 17, compiler cung cấp những thành phần tương ứng theo các rules của record:

- Private final component fields `x` và `y`.
- Một canonical constructor nhận giá trị cho toàn bộ components, nếu không được khai báo tường minh.
- Public accessors `x()` và `y()`, nếu không được viết tường minh.
- `equals(Object)`, `hashCode()`, `toString()` theo record components, nếu không được viết tường minh.

Một record class ngầm kế thừa `java.lang.Record`, không thể extends custom superclass và là final. Những điều này nằm trong record model, nhưng **bài học tập trung vào component accessors** chứ không đi sâu vào toàn bộ record lifecycle.

### 2.1. Record component không chỉ là một field

Trong:

~~~java
record OrderLine(String sku, int quantity) {
}
~~~

`sku` và `quantity` là **record components** ở declaration header. Với mỗi component, Java thiết lập một nhóm các phần liên quan gồm field, canonical constructor parameter và accessor method theo quy tắc. Người dùng nên gọi `line.sku()`/`line.quantity()`, thay vì cố đọc fields riêng tư.

### 2.2. Tại sao accessor khác getter?

Một record thể hiện “dữ liệu này gồm các thành phần nào” trực tiếp qua header. Nên accessor mang tên component, không cần suy từ property naming convention bên ngoài. Đây là API minh bạch đối với source code và reflection dành riêng cho record.

Một class JavaBeans truyền thống thường viết:

~~~java
class CustomerBean {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Getter `getName()` là method do developer/tool viết theo convention. Compiler Java **không tự thêm getter/setter** chỉ vì có field `name` trong class thường.

### 2.3. Record không có setter component mặc định

Với `record Point(int x, int y)`, gọi `point.setX(9)` sẽ không biên dịch trừ khi bạn tự viết một method `setX` khác. Component field là final, nên record không hỗ trợ setter thông thường để đổi giá trị component field sau construction.

Bạn có thể tạo một record **mới** với giá trị khác, chẳng hạn `new Point(9, point.y())`. Đây là lựa chọn điển hình khi modeling immutable value data.

## 3. Chương trình hoàn chỉnh 1: accessor mặc định

Tạo tệp **`RecordAccessorBasicsDemo.java`**:

~~~java
public class RecordAccessorBasicsDemo {
    record Member(String name, int age, boolean active) {
    }

    public static void main(String[] args) {
        Member member = new Member("Lan", 22, true);

        System.out.println("name = " + member.name());
        System.out.println("age = " + member.age());
        System.out.println("active = " + member.active());
        System.out.println("record = " + member);
        System.out.println("identity = "
                + member.equals(new Member("Lan", 22, true)));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 RecordAccessorBasicsDemo.java
java RecordAccessorBasicsDemo
~~~

**Stdout chính xác:**

~~~text
name = Lan
age = 22
active = true
record = Member[name=Lan, age=22, active=true]
identity = true
~~~

### 3.1. Những methods nào tồn tại?

`Member` có component accessors `name()`, `age()`, `active()` mà không cần code trong body. Chúng là public instance methods theo record rules.

### 3.2. Vì sao không có `getName()`?

Header `record Member(String name,...)` **không yêu cầu compiler tạo JavaBeans-style `getName()`**. Gọi `member.getName()` trong demo sẽ không compile nếu developer chưa khai báo method đó.

### 3.3. Vì sao một record khác nhưng bằng dữ liệu có equals true?

Default `equals` của record kiểm tra các component field values theo record equality semantics. Hai Member với cùng name, age và active là bằng nhau về value. `==` giữa hai objects được tạo bởi hai lần `new Member(...)` vẫn false vì đó là hai references riêng.

### 3.4. Vì sao tên record là Member trong toString?

Generated `toString` của record có dạng bao gồm tên record class và các component names/values; ở đây `Member[name=Lan, age=22, active=true]`. Accessor names trùng names của các components.

## 4. Chữ ký và phạm vi của implicit accessor

Với:

~~~java
public record Account(String id, long balance) {
}
~~~

(trong một tệp `Account.java` riêng nếu Account là top-level public type), các accessors có signatures tương ứng:

~~~java
public String id()
public long balance()
~~~

Những methods này:

1. Là **instance methods**, không phải static methods.
2. Có **public** access, dù chính record class có thể package-private.
3. Không nhận parameters.
4. Có return type **đúng kiểu của record component**.
5. Không khai báo type parameters riêng.
6. Không khai báo `throws` clause cho component accessor.
7. Có thể được **viết tường minh** nếu cần behavior có chủ đích, nhưng phải tuân theo các constraints.

### 4.1. Tên và kiểu phải khớp record component

Component `String id` có accessor `String id()`. Không thể biến nó thành `Object id()` chỉ vì String là subtype của Object, hoặc `CharSequence id()` để thu hẹp API. Return type của accessor phải **chính xác cùng type** với component (không chỉ compatible theo covariance).

### 4.2. Không thể hạ mức truy cập

Nếu record khai báo:

~~~java
record Item(String code) {
    String code() {
        return code;
    }
}
~~~

đoạn này **cố ý không biên dịch**: component accessor explicit phải là `public`; package-private không đủ.

Đúng:

~~~java
record Item(String code) {
    public String code() {
        return code;
    }
}
~~~

### 4.3. Không thể tạo static accessor cùng chữ ký

~~~java
record Item(String code) {
    public static String code() {
        return "X";
    }
}
~~~

**Cố ý không biên dịch**. Một component cần instance accessor; một static method cùng signature không thể phục vụ record accessor contract.

### 4.4. Không khai báo checked exception từ accessor

Một accessor tường minh như:

~~~java
record Data(String value) {
    public String value() throws java.io.IOException {
        return value;
    }
}
~~~

**Cố ý không biên dịch**: explicit record component accessor không được khai báo `throws` clause. Đây là constraint ngôn ngữ ngay cả khi method body thực tế không ném lỗi.

### 4.5. Không thể genericize accessor

Một component `String text` yêu cầu `String text()`. Không thể thay accessor bằng một method dạng `<T> T text()` để trả arbitrary type. Đây không phải method signature tương ứng với component.

## 5. Boolean accessor: `active()` khác `isActive()`

Một khác biệt thực tế rất thường gặp:

~~~java
record Feature(boolean enabled, Boolean verified) {
}
~~~

Accessor đúng là:

~~~java
feature.enabled();
feature.verified();
~~~

**Không phải**:

~~~java
feature.isEnabled();
feature.getVerified();
~~~

trừ khi developer tự cung cấp các methods đó.

### 5.1. Quy ước JavaBeans cho boolean

Một JavaBeans getter thường có dạng `isEnabled()` nếu property type là primitive `boolean`, hoặc `getEnabled()` theo convention tương ứng. Với wrapper type `Boolean`, `getVerified()` là cách phổ biến.

Một số thư viện có lựa chọn/naming strategies riêng; không được suy rằng **mọi framework** đều chỉ hỗ trợ một kiểu tên duy nhất.

### 5.2. Record vẫn đặt tên theo component

Record component `boolean isReady` sẽ có accessor `isReady()` vì **tên component thực sự là `isReady`**, không phải vì compiler áp dụng JavaBeans boolean naming. Đây là bẫy dễ gây nhầm:

~~~java
record State(boolean isReady) {
}
~~~

`state.isReady()` là record component accessor. Khi phản chiếu bằng JavaBeans convention, tên property được suy từ getter có thể khác cách record metadata định nghĩa component; framework có thể phải xử lý mapping.

Đặt component là `ready` rồi dùng `ready()` thường đơn giản hơn nếu domain model muốn tên data là ready.

### 5.3. Đừng xem `is` là một modifier trong record header

Trong `record State(boolean isReady)`, `isReady` là một Java identifier bình thường. Java compiler không tự cắt tiền tố `is` ra thành một component tên `ready`.

## 6. JavaBeans getter là một quy ước API

JavaBeans-style getters và setters được xác định qua naming/signature conventions trong JavaBeans ecosystem. Một property tên `firstName` thường được biểu diễn bằng:

~~~java
public String getFirstName()
public void setFirstName(String value)
~~~

Property boolean `active` có thể được đọc bằng `isActive()`:

~~~java
public boolean isActive()
~~~

Các công cụ JavaBeans truyền thống thường tìm property descriptors bằng cách phân tích các public methods theo convention.

### 6.1. Getter không cần tương ứng với field

Một Bean có thể viết:

~~~java
class RectangleBean {
    private int width;
    private int height;

    public int getArea() {
        return width * height;
    }
}
~~~

Method `getArea()` có thể được nhận diện như một **read-only property** tên `area` dù class không có field `area`. Đây là sự khác nhau quan trọng với **record component**: record component nằm trong header và luôn có state component tương ứng.

### 6.2. Getter chỉ đọc không nhất thiết có setter

JavaBeans-style property có thể read-only. Không phải mọi property đều cần cả getter lẫn setter:

~~~java
public String getCode() {
    return code;
}
~~~

Những libraries xử lý mutable Bean có thể yêu cầu no-arg constructor và setters; những libraries chỉ đọc có thể không cần. Đây là yêu cầu framework/application chứ không phải quy tắc bắt buộc của record.

### 6.3. JavaBeans naming có edge cases

Ví dụ acronym names (`getURL()`) và `Introspector.decapitalize` có naming behavior riêng. `getURL()` có thể tương ứng property tên `URL` chứ không nhất thiết `uRL`. Record thì ghi rõ component name trong header, không cần suy luận từ getter method name.

### 6.4. Getter và record accessor đều là methods Java

Hai kiểu này không khác bytecode vì một “không phải method”. `person.name()` và `bean.getName()` đều là instance method invocations theo Java. Khác biệt là **quy tắc sinh ra/chữ ký**, nguồn metadata và ecosystem conventions.

## 7. Chương trình hoàn chỉnh 2: Bean vs record gọi phương thức

Tạo tệp **`BeansVsRecordDemo.java`**:

~~~java
public class BeansVsRecordDemo {
    static final class CustomerBean {
        private String name;
        private boolean active;

        CustomerBean(String name, boolean active) {
            this.name = name;
            this.active = active;
        }

        public String getName() {
            return name;
        }

        public boolean isActive() {
            return active;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    record CustomerRecord(String name, boolean active) {
    }

    public static void main(String[] args) {
        CustomerBean bean = new CustomerBean("Mai", true);
        CustomerRecord record = new CustomerRecord("Mai", true);

        System.out.println("Bean name = " + bean.getName());
        System.out.println("Bean active = " + bean.isActive());
        System.out.println("Record name = " + record.name());
        System.out.println("Record active = " + record.active());

        bean.setName("An");
        System.out.println("Bean renamed = " + bean.getName());

        CustomerRecord changed = new CustomerRecord("An", record.active());
        System.out.println("New record = " + changed);
        System.out.println("Original record = " + record);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BeansVsRecordDemo.java
java BeansVsRecordDemo
~~~

**Stdout chính xác:**

~~~text
Bean name = Mai
Bean active = true
Record name = Mai
Record active = true
Bean renamed = An
New record = CustomerRecord[name=An, active=true]
Original record = CustomerRecord[name=Mai, active=true]
~~~

### 7.1. Bean có thể mutate state sau construction

`bean.setName("An")` thay field name của cùng CustomerBean object.

### 7.2. Record không có built-in setter

`CustomerRecord` có component field final, nên demo tạo object mới `changed` để biểu diễn name mới, còn `record` gốc giữ "Mai".

### 7.3. Vì sao naming convention không quyết định mutability?

JavaBeans có thể là read-only và record có thể chứa nested mutable objects. Getter prefix bản thân không làm class mutable; component accessor name() bản thân cũng không làm toàn bộ object graph immutable. Mutability đến từ fields, referenced objects, constructors và API.

## 8. JavaBeans introspection và record component reflection là hai nguồn metadata

Java 17 có những APIs phản chiếu record-specific:

~~~java
SomeRecord.class.isRecord()
SomeRecord.class.getRecordComponents()
~~~

Với `java.lang.reflect.RecordComponent`, ta có thể đọc:

- `getName()` — tên component.
- `getType()` — runtime Class cho kiểu component.
- `getGenericType()` — thông tin type generic.
- `getAccessor()` — Method của component accessor.
- Annotations liên quan theo targets và rules.

Trong khi đó, JavaBeans có:

~~~java
java.beans.Introspector.getBeanInfo(SomeClass.class)
~~~

và các `PropertyDescriptor`, với naming conventions `getX()`/`isX()`. Đối với Java 17 standard JavaBeans Introspector, **một bare record không tự xuất hiện như một bộ JavaBeans properties chỉ nhờ component methods `x()`**. Những frameworks hiện đại có thể có **record-aware handling riêng**, nên không suy rằng một library bất kỳ cũng hành xử y hệt Introspector.

### 8.1. `Introspector.getBeanInfo(type, Object.class)`

Dùng `Object.class` làm stop class giúp tránh inherited Object-level descriptors như `class` trong output, nhờ đó nhìn rõ properties có getter của type đang xét.

### 8.2. Record reflection không phụ thuộc tên getter JavaBeans

`RecordComponent.getAccessor()` trả method `name()`, `age()`, v.v. Nhờ vậy một framework record-aware có thể truy cập components đúng theo Java language model mà không cần đoán tiền tố get/is.

### 8.3. Module dependency cần lưu ý

`java.beans` nằm trong module `java.desktop` của JDK. Với **named modules**, code sử dụng `java.beans.Introspector` cần đọc module java.desktop (`requires java.desktop;` trong module-info.java nếu chưa readable theo module graph). Record reflection APIs `java.lang.Class`/`java.lang.reflect.RecordComponent` thuộc nền tảng Java thông thường.

## 9. Chương trình hoàn chỉnh 3: JavaBeans Introspector vs record reflection

Tạo tệp **`BeanIntrospectionDemo.java`**:

~~~java
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.List;

public class BeanIntrospectionDemo {
    public static final class BeanItem {
        private final String sku;
        private final boolean available;

        public BeanItem(String sku, boolean available) {
            this.sku = sku;
            this.available = available;
        }

        public String getSku() {
            return sku;
        }

        public boolean isAvailable() {
            return available;
        }
    }

    public record PlainRecord(String sku, boolean available) {
    }

    public record BridgedRecord(String sku, boolean available) {
        public String getSku() {
            return sku();
        }

        public boolean isAvailable() {
            return available();
        }
    }

    static List<String> beanProperties(Class<?> type) throws Exception {
        return Arrays.stream(Introspector.getBeanInfo(
                        type, Object.class).getPropertyDescriptors())
                .map(PropertyDescriptor::getName)
                .sorted()
                .toList();
    }

    static List<String> componentNames(Class<?> type) {
        RecordComponent[] components = type.getRecordComponents();
        if (components == null) {
            return List.of();
        }

        return Arrays.stream(components)
                .map(RecordComponent::getName)
                .toList();
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Bean properties = "
                + beanProperties(BeanItem.class));
        System.out.println("Plain record properties = "
                + beanProperties(PlainRecord.class));
        System.out.println("Bridged record properties = "
                + beanProperties(BridgedRecord.class));
        System.out.println("Record components = "
                + componentNames(PlainRecord.class));
        System.out.println("Record accessor = "
                + PlainRecord.class.getRecordComponents()[0]
                        .getAccessor().getName());
    }
}
~~~

Biên dịch/chạy bằng **JDK 17**:

~~~bash
javac -encoding UTF-8 BeanIntrospectionDemo.java
java BeanIntrospectionDemo
~~~

**Stdout dự kiến trên JDK 17 chuẩn:**

~~~text
Bean properties = [available, sku]
Plain record properties = []
Bridged record properties = [available, sku]
Record components = [sku, available]
Record accessor = sku
~~~

### 9.1. Vì sao plain record properties rỗng?

`PlainRecord` có `sku()` và `available()` nhưng không có `getSku()` hay `isAvailable()`. JavaBeans Introspector theo convention của JDK 17 không diễn giải các component-named methods này như JavaBeans getters.

### 9.2. Vì sao bridged record được nhận diện?

`BridgedRecord` tự khai báo `getSku()` và `isAvailable()`, nên Introspector có thể tìm ra các JavaBeans properties theo getter naming convention. Record vẫn có component accessors `sku()` và `available()` song song.

### 9.3. Vì sao componentNames đúng cho plain record?

Record reflection đọc metadata record components từ class file, không cần JavaBeans getter convention. Nó trả declaration order `[sku, available]`.

### 9.4. Giới hạn khi kiểm tra frameworks thực tế

Output `Introspector` trong demo phản ánh **standard JavaBeans API trên Java 17**. Jackson, Spring, Jakarta frameworks, Hibernate, build-time mappers hay IDEs có thể dùng introspection riêng, annotations, method handles hoặc record component APIs. Muốn biết một phiên bản framework cụ thể có hỗ trợ record không, cần test integration với chính framework và version đó; không kết luận từ Introspector duy nhất.

## 10. Explicit accessor trong record: có thể viết, nhưng phải đúng contract

Bạn có thể viết accessor tường minh:

~~~java
record Greeting(String message) {
    public String message() {
        return message.trim();
    }
}
~~~

`message()` này thay implementation accessor mặc định. Nó **không** thêm component mới và **không** thay field `message` vốn đã được canonical constructor gán.

Các trường hợp hợp lệ cần bảo đảm:

- Method là `public`.
- Method không `static`.
- Không có parameters.
- Return type chính xác là component type.
- Không khai báo type parameters/throws clause.
- Nếu muốn trả state thực tế, thường đọc component field hoặc một representation phù hợp.
- Việc khác giá trị field phải được thiết kế có chủ đích vì có thể tạo khác biệt giữa accessor và các methods sinh tự động khác.

### 10.1. Explicit accessor có thể tính toán giá trị

Một record có thể viết:

~~~java
record Person(String name) {
    public String name() {
        return name.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Đây là record declaration fragment. Khi gọi `person.name()`, kết quả uppercase; nhưng **component field name** vẫn chứa value constructor đã gán, nếu không được normalize ở constructor.

### 10.2. Không nhầm overridden accessor với setter

Accessor vẫn nhận 0 tham số và trả type thành phần. Nó không thể thay đổi component final field sau construction, dù có code logic tùy chỉnh. Method `withName(String)` tạo record mới có thể hợp lệ như một pattern value update.

### 10.3. Vì sao không nên lạm dụng biến đổi ở accessor?

Một record được hiểu như một giá trị gồm các components. Nếu `name()` trả một giá trị khác hẳn component field, developer có thể bất ngờ khi so `equals`/`hashCode`/`toString` với kết quả accessor. Thông thường nên **normalize/validate tại canonical constructor**, để field và accessor cùng thể hiện một state thống nhất.

## 11. `equals()`, `hashCode()` và `toString()` sinh tự động nhìn vào gì?

Đây là chi tiết rất quan trọng của Java records.

**Các implementations sinh tự động của `equals()`, `hashCode()` và `toString()` dựa trên các component fields, không bắt buộc gọi custom accessor methods.** Vì vậy nếu bạn tự viết `String name()` trả một String đã trim nhưng field vẫn chứa spaces, generated equality/toString vẫn xét raw field value.

### 11.1. Ví dụ hai bản ghi có accessor giống nhau nhưng không equals

Tệp **`RecordAccessorNormalizationDemo.java`**:

~~~java
public class RecordAccessorNormalizationDemo {
    record Raw(String text) {
        public String text() {
            return text.trim();
        }
    }

    record Normalized(String text) {
        Normalized {
            text = text.trim();
        }
    }

    public static void main(String[] args) {
        Raw rawA = new Raw(" A ");
        Raw rawB = new Raw("A");

        System.out.println("Raw accessor = " + rawA.text());
        System.out.println("Raw equal accessor values = "
                + rawA.text().equals(rawB.text()));
        System.out.println("Raw equals = " + rawA.equals(rawB));
        System.out.println("Raw toString = " + rawA);

        Normalized normalizedA = new Normalized(" A ");
        Normalized normalizedB = new Normalized("A");

        System.out.println("Normalized accessor = "
                + normalizedA.text());
        System.out.println("Normalized equals = "
                + normalizedA.equals(normalizedB));
        System.out.println("Normalized toString = " + normalizedA);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 RecordAccessorNormalizationDemo.java
java RecordAccessorNormalizationDemo
~~~

**Stdout chính xác:**

~~~text
Raw accessor = A
Raw equal accessor values = true
Raw equals = false
Raw toString = Raw[text= A ]
Normalized accessor = A
Normalized equals = true
Normalized toString = Normalized[text=A]
~~~

### 11.2. Vì sao Raw accessor trả A mà equals false?

`Raw(" A ")` lưu field `text` có khoảng trắng hai đầu, nhưng custom accessor chỉ trim **khi trả ra**. `Raw("A")` lưu field text khác. Generated equals so fields nên hai records không bằng nhau.

### 11.3. Vì sao toString vẫn có spaces?

Generated toString đọc state của component fields; custom accessor không thay storage state. Do đó `Raw[text= A ]` chứa khoảng trắng như raw field.

### 11.4. Vì sao compact canonical constructor tốt hơn cho normalize?

Trong `Normalized`, compact constructor `Normalized { text = text.trim(); }` chỉnh constructor parameter trước khi canonical constructor gán vào final component field. Kết quả field thực sự chứa "A". Accessor mặc định, equals và toString đều phản ánh normalized representation.

### 11.5. Khi nào custom accessor vẫn hợp lý?

- Defensive copy của mutable component.
- Trả projection được quy định rõ trong API và chấp nhận field khác.
- Che giấu nội bộ một mutable representation theo contract (nhưng cần xem xét record equality/toString semantics).
- Bổ sung behavior đặc thù mà record component chính xác vẫn giữ type.

Với mutable object, hãy đảm bảo constructor và accessor cùng bảo vệ ownership, không chỉ một phía.

## 12. Record là shallow immutable, không tự deep immutable

Record component fields là final, nhưng **referent của field kiểu tham chiếu vẫn có thể mutable**.

Ví dụ:

~~~java
record Group(java.util.List<String> names) {
}
~~~

`Group.names()` trả List reference đã được lưu. Nếu caller giữ alias tới một `ArrayList` rồi gọi `add()`, record có thể quan sát thay đổi sau construction. Nếu caller gọi `group.names().add(...)` và List mutable, họ cũng có thể thay internal state.

Vì vậy câu “record là immutable” cần phân biệt:

1. **Field reference không thể được gán lại sau construction**.
2. **Object được field trỏ tới có thể mutable**.
3. Record không tự defensive-copy arrays/Lists/maps/nested objects.
4. Generated equals/hashCode có thể phụ thuộc vào mutable state hoặc identity của referenced objects.
5. Một custom accessor có thể làm defensive copy nhưng không làm nested state sâu tự immutable.

### 12.1. `List.copyOf` cho unmodifiable structural snapshot

Một record có List<String> có thể viết:

~~~java
record Tags(java.util.List<String> values) {
    Tags {
        values = java.util.List.copyOf(values);
    }
}
~~~

Sau construction, internal List là unmodifiable structural snapshot theo contract của `List.copyOf`. Nếu source List được sửa sau đó, record List không đổi (giả sử elements immutable Strings). Accessor mặc định `values()` trả internal unmodifiable List; không cần copy lại mỗi lần.

### 12.2. Những điều `List.copyOf` không làm

- Không nhận null elements.
- Không deep-copy mutable element objects.
- Không tự biến mutable objects chứa trong List thành immutable.
- Có thể reuse một phù hợp immutable/unmodifiable input List thay vì luôn cấp phát List mới.

Khi record component có mutable elements, hãy cân nhắc immutable DTOs hoặc defensive copying tới đúng độ sâu ownership cần thiết.

### 12.3. Array cần bảo vệ cả constructor lẫn accessor

Một `byte[]` là mutable object. Nếu chỉ clone trong constructor nhưng accessor trả field trực tiếp, caller có thể sửa record state từ bên ngoài. Nếu chỉ clone trong accessor nhưng constructor lưu input array gốc, caller vẫn có thể sửa array qua alias ban đầu.

Cần **copy on input và copy on output** nếu muốn tránh external mutations.

## 13. Chương trình hoàn chỉnh 5: defensive copy cho List và array

Tạo tệp **`RecordDefensiveAccessorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RecordDefensiveAccessorDemo {
    record Tags(String owner, List<String> values) {
        Tags {
            Objects.requireNonNull(owner);
            values = List.copyOf(values);
        }
    }

    record Packet(byte[] payload) {
        Packet {
            payload = Objects.requireNonNull(payload).clone();
        }

        public byte[] payload() {
            return payload.clone();
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("A"));
        Tags tags = new Tags("Lan", input);

        input.add("B");
        System.out.println("Saved tags = " + tags.values());

        try {
            tags.values().add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Tags unmodifiable");
        }

        byte[] source = {1, 2};
        Packet packet = new Packet(source);
        source[0] = 9;

        System.out.println("After input mutation = "
                + Arrays.toString(packet.payload()));

        byte[] output = packet.payload();
        output[1] = 7;

        System.out.println("After accessor mutation = "
                + Arrays.toString(packet.payload()));

        Packet sameContents = new Packet(new byte[]{1, 2});
        System.out.println("Arrays equal by record equals = "
                + packet.equals(sameContents));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 RecordDefensiveAccessorDemo.java
java RecordDefensiveAccessorDemo
~~~

**Stdout chính xác:**

~~~text
Saved tags = [A]
Tags unmodifiable
After input mutation = [1, 2]
After accessor mutation = [1, 2]
Arrays equal by record equals = false
~~~

### 13.1. Vì sao Tags không đổi khi input.add?

Compact canonical constructor dùng `List.copyOf(values)` tạo structural snapshot của initial List. `input.add("B")` không làm snapshot bên trong record thay đổi.

### 13.2. Vì sao accessor `values()` không cần tự override?

Bên trong Tags đã lưu unmodifiable List<String> với immutable String elements cho contract của demo. Accessor mặc định trả cùng List là an toàn trước mutation cấu trúc từ bên ngoài.

### 13.3. Vì sao Packet phải override `payload()`?

`payload` là byte[] mutable. Constructor đã clone input, nhưng không clone ở accessor thì caller có thể làm `packet.payload()[0] = 9` thay internal array. Custom public `payload()` trả clone để caller chỉ sửa bản sao.

### 13.4. Vì sao hai Packet có cùng bytes mà equals false?

Generated equality cho array component dùng **reference equality của array**, không tự dùng `Arrays.equals` theo nội dung. Hai Packet constructors clone hai arrays khác nhau; do đó generated equals false ngay cả khi bytes giống nhau.

Nếu value semantics thực sự phải dựa trên array contents, cần design custom equality/hashCode đúng contract hoặc chuyển sang một immutable value representation phù hợp. Không thể chỉ custom accessor là đủ: generated equality vẫn đọc raw fields.

### 13.5. Bẫy lưu state mutable và hash-based collections

Nếu một record giữ mutable List/Map/array và các fields đó thay qua alias, hashCode của record có thể thay theo nested object's hash behavior, gây lỗi nếu record đã là key trong HashMap. Với array, default hashCode thường theo reference identity chứ không theo content; sự bất ngờ khác lại xảy ra. Hãy định nghĩa value semantics và ownership trước khi dùng record làm key.

## 14. Vì sao không nên dùng accessor để sửa state?

Một component field là final; setter thông thường không thể thay nó. Accessor được thiết kế để **đọc** component value, không phải để cập nhật record.

~~~java
record Point(int x, int y) {
    Point withX(int nextX) {
        return new Point(nextX, y);
    }
}
~~~

`withX` là method bình thường tạo **record mới**. Đây là lựa chọn thích hợp cho immutable value records.

Đừng viết một method `public int x()` có side effects chỉ để biến việc “đọc x” thành một phép mutate bất ngờ. Dù Java cho phép code arbitrary trong explicit accessor, logic gây side effects khiến debugging, caching và equality rất khó hiểu.

### 14.1. Nếu record thực sự cần mutable collaborators

Ví dụ component `AtomicInteger counter` cho phép thay state bên trong referent dù record field final. Lúc đó record không còn deep immutable; phải công bố rõ concurrency/ownership semantics. Tránh chọn record chỉ vì muốn ít boilerplate nếu domain là mutable entity có lifecycle và setters.

### 14.2. Canonical constructor là điểm tốt để validate

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }
}
~~~

Sau successful construction, invariant `start <= end` luôn đúng với component fields. Accessors mặc định trả dữ liệu hợp lệ mà không cần validate lại mỗi lần đọc.

### 14.3. Không nhầm constructor normalization với display formatting

Nếu cần giữ raw data để audit nhưng UI muốn formatted version, giữ accessor mặc định `rawName()` và thêm method `displayName()`. Không nên thay nghĩa component `name()` một cách mơ hồ nếu generated equality/toString vẫn theo raw field.

## 15. Thêm JavaBeans-style getters vào record khi thật sự cần

Một record có thể khai báo **extra methods** mang tên JavaBeans:

~~~java
record Product(String sku, boolean available) {
    public String getSku() {
        return sku();
    }

    public boolean isAvailable() {
        return available();
    }
}
~~~

Đây là record declaration fragment. Compiler vẫn cung cấp `sku()` và `available()`. Bạn thêm `getSku()`/`isAvailable()` để một API/client JavaBeans-style có thể đọc property theo convention.

### 15.1. Đây là bridge, không phải accessor replacement

`getSku()` không phải component accessor của `sku`. Nếu bạn viết `getSku()` nhưng bỏ `sku()`, implicit `sku()` vẫn có mặt. Nếu bạn viết explicit `sku()` riêng, phải tuân constraints của accessor.

### 15.2. Không cần setters để là read-only Bean properties

`Product` không thể mutate component fields bằng setters sau construction. Thêm `getSku` có thể giúp công cụ **read** property nhưng không giúp frameworks yêu cầu writable setters hoặc no-arg constructor. Những frameworks như vậy có thể vẫn không dùng được record trừ khi có record-specific support.

### 15.3. Tránh duplicate JSON properties không mong muốn

Một framework có thể phát hiện record components qua reflection và đồng thời phát hiện getX/isX methods qua JavaBeans convention. Nếu bạn thêm bridge getters, nó có thể thấy các property paths trùng/khác tên, hoặc áp dụng annotations khác nhau tùy framework. Nên thử serialization/deserialization thực tế và cấu hình naming/annotations phù hợp; đừng assume mọi framework sẽ tự deduplicate đúng.

### 15.4. Khi nào thêm bridge?

- Giao tiếp với legacy component yêu cầu phương thức `getX()`.
- Triển khai interface đã có contract getter JavaBeans.
- Một tool làm introspection chỉ theo JavaBeans getter naming mà không hỗ trợ records.
- Giữ tương thích khi chuyển một API từ ordinary class sang record, nếu behavior/signatures cũ cần duy trì.

Ngược lại, nếu cả codebase/mapper đã hỗ trợ records, tránh thêm getter boilerplate không cần thiết.

## 16. Chương trình hoàn chỉnh 6: record implement hai interface naming contracts

Tạo tệp **`RecordInterfaceBridgeDemo.java`**:

~~~java
public class RecordInterfaceBridgeDemo {
    interface ComponentNamed {
        String name();
    }

    interface LegacyNamed {
        String getName();
    }

    record Member(String name)
            implements ComponentNamed, LegacyNamed {

        @Override
        public String getName() {
            return name();
        }
    }

    public static void main(String[] args) {
        Member member = new Member("Mai");

        ComponentNamed modern = member;
        LegacyNamed legacy = member;

        System.out.println("Component accessor = " + member.name());
        System.out.println("Modern interface = " + modern.name());
        System.out.println("Legacy interface = " + legacy.getName());
        System.out.println("Same object = " + (modern == legacy));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 RecordInterfaceBridgeDemo.java
java RecordInterfaceBridgeDemo
~~~

**Stdout chính xác:**

~~~text
Component accessor = Mai
Modern interface = Mai
Legacy interface = Mai
Same object = true
~~~

### 16.1. Record accessor có thể thực hiện interface method

`Member.name()` được compiler cung cấp và là public; nó tương ứng method `ComponentNamed.name()` trong interface. Không cần khai báo explicit method chỉ để implement interface này.

### 16.2. JavaBeans-style interface cần bridge rõ

`LegacyNamed.getName()` không trùng component accessor `name()`. Do đó Member tự khai báo `getName()` và dùng `name()` để trả component value.

### 16.3. Vì sao hai interface references vẫn là một object?

`modern` và `legacy` cùng trỏ đến `member`. `modern == legacy` true (hai references của interface types có liên hệ qua implementor; Java cho phép so identity trong trường hợp này). Interface naming conventions không tạo object mới.

## 17. Method references và Stream APIs sử dụng accessor như ordinary method

Record accessor là một instance method không tham số, vì vậy rất phù hợp với method reference:

~~~java
record User(String name, int age) {
}

java.util.function.Function<User, String> readName = User::name;
~~~

`User::name` là reference đến accessor `name()`. Tương đương ý nghĩa đọc tên như lambda `user -> user.name()`.

Với JavaBeans class, method reference sẽ là `CustomerBean::getName`.

### 17.1. Stream mapping

~~~java
List<String> names = users.stream()
        .map(User::name)
        .toList();
~~~

Java biết `User::name` trả String nên method reference phù hợp với `Function<User,String>`.

### 17.2. Sorting qua accessor

~~~java
users.stream()
        .sorted(Comparator.comparing(User::name))
        .toList();
~~~

Comparator dùng name values trả về từ accessor. Nếu accessor có normalization hoặc side effects, behavior sorting có thể khác raw component fields, nên cần thiết kế accessor deterministic và phù hợp.

### 17.3. Phân biệt với field reference

Java không có source syntax `User::nameField` cho arbitrary field getter như method reference. Record cung cấp method `name()` sẵn, nên có thể dùng `User::name` trực tiếp.

## 18. Chương trình hoàn chỉnh 7: accessor method references

Tạo tệp **`RecordMethodReferenceDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.function.Function;

public class RecordMethodReferenceDemo {
    record User(String name, int age) {
    }

    public static void main(String[] args) {
        List<User> users = List.of(
                new User("Mai", 25),
                new User("An", 20));

        Function<User, String> readName = User::name;

        System.out.println("Reference = "
                + readName.apply(users.get(0)));

        System.out.println("Names = "
                + users.stream().map(User::name).toList());

        System.out.println("Sorted = "
                + users.stream()
                        .sorted(Comparator.comparing(User::name))
                        .map(User::name)
                        .toList());

        System.out.println("Ages = "
                + users.stream().map(User::age).toList());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 RecordMethodReferenceDemo.java
java RecordMethodReferenceDemo
~~~

**Stdout chính xác:**

~~~text
Reference = Mai
Names = [Mai, An]
Sorted = [An, Mai]
Ages = [25, 20]
~~~

### 18.1. Không cần `getName` cho các method references

`User::name` là public accessor thực sự tồn tại trong compiled record. Java compiler không cần bridge getter.

### 18.2. Sorting không sửa original List

`stream().sorted(...)` tạo một stream có thứ tự mới; `toList()` lấy kết quả. `users` vẫn là List.of tạo từ input ban đầu [Mai, An]. Output Sorted [An, Mai] do comparator theo String name.

### 18.3. Tránh methods có side effects khi sorting

Một comparator có thể gọi accessor nhiều lần. Nếu explicit accessor thay state hoặc trả giá trị không ổn định theo các lần gọi, comparator có thể vi phạm contract, gây kết quả bất thường. Thực hành tốt là giữ component accessors thuần, không side effects.

## 19. Reflection: record component API là bằng chứng chuẩn

Dùng `Class.isRecord()` để xác định type là record, và `Class.getRecordComponents()` để lấy components theo declaration order.

Ví dụ:

~~~java
record Coordinates(int row, int col) {
}
~~~

Bạn có thể lấy:

~~~java
RecordComponent[] components =
        Coordinates.class.getRecordComponents();
~~~

Mỗi RecordComponent có `getAccessor()` trả Method public. Tên accessor phải đúng tên component.

### 19.1. Chương trình hoàn chỉnh 8: introspection qua RecordComponent

Tạo tệp **`RecordReflectionDemo.java`**:

~~~java
import java.lang.reflect.Modifier;
import java.lang.reflect.RecordComponent;

public class RecordReflectionDemo {
    record Coordinates(int row, int col) {
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Coordinates.class;

        System.out.println("is record = " + type.isRecord());

        for (RecordComponent component
                : type.getRecordComponents()) {
            System.out.println(
                    component.getName()
                    + ":" + component.getType().getSimpleName()
                    + ":" + component.getAccessor().getName());
            System.out.println("public accessor = "
                    + Modifier.isPublic(
                            component.getAccessor().getModifiers()));
        }

        System.out.println("Has row() = "
                + (type.getDeclaredMethod("row") != null));

        try {
            type.getDeclaredMethod("getRow");
        } catch (NoSuchMethodException ex) {
            System.out.println("No getRow() by default");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 RecordReflectionDemo.java
java RecordReflectionDemo
~~~

**Stdout chính xác:**

~~~text
is record = true
row:int:row
public accessor = true
col:int:col
public accessor = true
Has row() = true
No getRow() by default
~~~

### 19.2. `getDeclaredMethod("row")` khác JavaBeans convention

Reflection gọi đúng method name `row` mà compiler sinh cho record. `getDeclaredMethod("getRow")` không tìm được method vì không có JavaBeans getter mặc định.

### 19.3. Component order có ý nghĩa

RecordComponent[] được trả theo declaration order trong record header. Thứ tự này liên quan canonical constructor parameters và generated `toString` representation; giữ mapping theo metadata, đừng tự sort alphabetical nếu không có requirement.

### 19.4. Với generic components

`component.getType()` cho raw runtime Class. `getGenericType()` cung cấp generic type metadata khi phù hợp, chẳng hạn List<String>. Nếu xây serializer/mapper, đọc đúng metadata để tránh mất type information.

## 20. Những lỗi biên dịch điển hình

### 20.1. Gọi getX trên record không có bridge

~~~java
record User(String name) {}

User u = new User("Lan");
System.out.println(u.getName()); // Cố ý không biên dịch.
~~~

**Sửa:** gọi `u.name()` hoặc bổ sung `getName()` với lý do tương thích API thực sự.

### 20.2. Gọi component accessor như field public

~~~java
record User(String name) {}

User u = new User("Lan");
System.out.println(u.name); // Cố ý lỗi truy cập private field.
~~~

**Sửa:** gọi `u.name()`. Record component fields là private final theo contract.

### 20.3. Định nghĩa explicit accessor không public

~~~java
record User(String name) {
    String name() { // Cố ý không biên dịch.
        return name;
    }
}
~~~

**Sửa:** `public String name()`.

### 20.4. Trả kiểu khác component

~~~java
record User(String name) {
    public Object name() { // Cố ý không biên dịch.
        return name;
    }
}
~~~

**Sửa:** return type chính xác `String`.

### 20.5. Thêm throws clause

~~~java
record User(String name) {
    public String name() throws Exception { // Cố ý không biên dịch.
        return name;
    }
}
~~~

**Sửa:** accessor không khai báo `throws` clause; validate/copy tại constructor hoặc dùng method khác với contract phù hợp.

### 20.6. Coi boolean record accessor là isX tự động

~~~java
record Flag(boolean ready) {}
Flag f = new Flag(true);
System.out.println(f.isReady()); // Cố ý không biên dịch.
~~~

**Sửa:** `f.ready()` hoặc bridge `isReady()` tự định nghĩa.

### 20.7. Cố thay component field từ setter

~~~java
record User(String name) {
    public void setName(String value) {
        name = value; // Cố ý không biên dịch; component field final.
    }
}
~~~

**Sửa:** tạo record mới thay vì mutate component field.

### 20.8. Tin rằng custom accessor normalize cả equality

Với `record Raw(String s){ public String s(){return s.trim();}}`, generated equals vẫn xét raw stored fields. **Sửa:** normalize s trong canonical constructor nếu invariant đòi stored field cũng normalized.

## 21. So sánh thiết kế record với JavaBeans class truyền thống

| Tiêu chí | Record | JavaBeans class thông thường |
| --- | --- | --- |
| Data declaration | Header `record User(String name, ...)` | Fields, constructors, accessor methods |
| Accessor mặc định | `name()` | Không có compiler-generated getter mặc định |
| Getter convention | Không phải `getName()` mặc định | Thường `getName()` |
| Boolean getter | `active()` | Thường `isActive()` |
| Component fields | Private final | Tùy class design |
| Setter để cập nhật field | Không có component setter mặc định | Có thể cung cấp setter |
| Canonical constructor | Gắn với record components | Không có record-specific canonical constructor |
| Generated equality/hashCode/toString | Có theo record fields | Không tự sinh theo fields |
| Reflection chuyên dụng | `isRecord()`, `getRecordComponents()` | JavaBeans Introspector convention, ordinary reflection |
| JavaBeans Introspector JDK 17 | Không tự phát hiện plain component accessors như get/is properties | Phát hiện getter-style properties |
| Method reference | `User::name` | `BeanUser::getName` |
| Custom getter | Có thể bổ sung `getName` | Là implementation chính theo convention |
| Deep immutability | Không tự bảo đảm | Cũng không tự bảo đảm |
| Framework binding | Cần record support hoặc bridge phù hợp | Thường hỗ trợ JavaBeans getter/setter |

### 21.1. Record không phải “Bean viết ngắn”

Record là một loại class với state description cố định, canonical constructor và value-like methods. Nó không có tất cả conventions của mutable JavaBean: no-arg constructor, setters, property change listeners, v.v. không được tự sinh.

### 21.2. JavaBeans không bắt buộc mutable

Một Bean có thể có read-only properties hoặc immutable state với constructor injection; JavaBeans getter naming không đồng nghĩa “mọi Bean phải có setter”. Nhưng nhiều frameworks cũ giả định no-arg constructor/setters và có thể cần adaptation khi dùng records.

### 21.3. Record phù hợp cho loại dữ liệu nào?

- DTOs và API response/request models với known components.
- Immutable value-like models, khi nested components được quản lý.
- Tuples/keys mang danh tính giá trị.
- Intermediate results khi code cần rõ names/types mà không cần mutable lifecycle.

### 21.4. Khi nào class + JavaBeans getters dễ tương thích hơn?

- Framework legacy chỉ đọc JavaBeans getter/setter.
- Mutable entity có persistence lifecycle phức tạp.
- Domain model cần inheritance từ một custom class.
- API bắt buộc no-arg constructor và property setters.

Chọn theo contract, không chỉ theo số dòng code.

## 22. Frameworks và serialization: tránh suy diễn quá mức

Nhiều frameworks hiện đại nhận diện records bằng reflection hoặc hỗ trợ record canonical constructor, nhưng **khả năng đó phụ thuộc phiên bản** và cấu hình:

- Một serializer có thể nhìn vào record components và lấy values bằng `component.getAccessor()`.
- Một legacy Bean mapper có thể chỉ tìm `getName()/isActive()` rồi thấy thiếu properties.
- Một deserializer có thể cần gọi canonical constructor, không thể set private final fields theo cách Bean thông thường.
- Một UI binding library có thể dựa trên PropertyDescriptor conventions.
- Annotations có target khác nhau (FIELD, METHOD, PARAMETER, RECORD_COMPONENT, TYPE_USE), nên vị trí annotation trên record component có thể ảnh hưởng propagation/metadata mà library đọc.
- Một library có thể tạo JavaBeans-like property descriptions cho records bằng logic riêng, độc lập `Introspector` JDK 17.

### 22.1. Quy trình kiểm tra compatibility

1. Xác định phiên bản JDK target và framework.
2. Xem framework có native record support không.
3. Kiểm tra serialization đọc `name()` hay `getName()`.
4. Kiểm tra deserialization có hỗ trợ canonical constructor không.
5. Xác nhận annotations đặt đúng target/mapping.
6. Viết integration test round-trip với dữ liệu thật.
7. Chỉ bổ sung bridge getters/adapters khi có lợi ích rõ.

### 22.2. Không tạo setters rỗng để “làm framework vui”

Với record, component fields final; không thể thực sự set lại. Một `setName` no-op sẽ làm tools tưởng object mutable trong khi dữ liệu không đổi, nguy hiểm hơn là yêu cầu adapter đúng. Nếu framework đòi setters, dùng DTO class phù hợp hoặc nâng cấp/configure record-aware binding.

### 22.3. Các generated methods không bảo đảm JSON key convention

JSON key naming do serializer configuration và annotations quyết định. Đừng suy rằng Java `name()` chắc chắn serialize thành `name` với mọi library. Ngược lại, đừng kết luận records luôn không serialize được chỉ vì thiếu `getName`.

## 23. Null, Optional và validation

Một component accessor có thể trả null nếu component field được lưu null; record không tự enforce non-null:

~~~java
record User(String name) {
}

User u = new User(null);
System.out.println(u.name() == null); // true
~~~

Nếu business invariant cấm null, validate trong canonical constructor:

~~~java
record User(String name) {
    User {
        java.util.Objects.requireNonNull(name, "name");
    }
}
~~~

### 23.1. Đừng tự bọc mọi accessor thành Optional

Nếu component type là String, accessor phải trả String, không thể tường minh sửa signature thành `Optional<String> name()`. Nếu muốn Optional view, tạo method khác `optionalName()` hoặc declare component itself as Optional<String> theo thiết kế API phù hợp.

### 23.2. Getter JavaBeans cũng không tự validate

`getName()` có thể trả null, throw exception, compute dynamic value hoặc đọc database nếu developer viết như vậy. Naming convention không trao bất kỳ non-null guarantee đặc biệt nào. Validation thuộc constructor, field/invariant và API contracts.

### 23.3. Compact constructor và null

Nếu record component type là List, `List.copyOf(null)` sẽ ném NPE; có thể dùng `Objects.requireNonNull` với message rõ ràng nếu muốn. Việc reject null nên được công bố như record constructor contract, không chỉ là một side effect tình cờ của accessor.

## 24. Kiểm thử record accessors đúng cách

Khi test:

~~~java
record Item(String id, int amount) {
}
~~~

cần xét:

1. `item.id()` và `item.amount()` trả expected values.
2. Component accessor methods là public và có đúng return type.
3. JavaBeans getX/isX không tồn tại nếu không được thêm.
4. `RecordComponent.getAccessor()` trỏ method chính xác.
5. Constructor validation/normalization được kiểm thử.
6. Defensive copies bảo vệ input và output nếu components mutable.
7. Generated equals/hashCode/toString có semantics phù hợp raw fields.
8. Khi explicit accessor biến đổi result, tests phải xem generated methods có dùng raw field.
9. JavaBeans bridge getters nếu tồn tại phải trả cùng logical values như component accessors theo contract.
10. Integration test với actual serializer/framework/version, không chỉ test reflection.
11. Method references `Item::id` compile và hoạt động.
12. Records không có setter mặc định và không thể mutate final component fields.

### 24.1. Không chỉ test `record.toString()`

Generated toString có thể phản ánh field raw ngay cả khi custom accessor trả normalized view. Đừng dùng toString như bằng chứng mọi accessors đã chuẩn hóa.

### 24.2. Không chỉ test equality

Generated equality có thể true/false theo component fields trong khi custom accessor tính toán khác. Cần test cả state consistency và equality contract theo domain.

### 24.3. Với byte[] component

Một test `packet.payload()[0] = 99` rồi đọc lại để xác nhận defensive copy là cần thiết. Đồng thời test constructor alias `input[0]=99` sau khi tạo record. Chỉ test một phía sẽ bỏ sót vulnerability ở phía còn lại.

## 25. Sai lầm thường gặp

1. **Gọi `getName()` trên record bare:** Compiler chỉ sinh `name()`.
2. **Gọi `isActive()` cho `boolean active`:** Record sinh `active()`.
3. **Coi record component là public field:** Field là private final.
4. **Tưởng Java compiler tự tạo JavaBeans getter:** Không, trừ khi tool/library riêng can thiệp.
5. **Coi mọi Bean đều mutable:** Getter-only Bean cũng tồn tại.
6. **Coi mọi record deep immutable:** Mutable List/array components vẫn có thể thay.
7. **Viết explicit accessor package-private:** Phải public.
8. **Viết explicit accessor kiểu trả Object cho String component:** Sai return type.
9. **Thêm throws clause cho accessor:** Sai record-specific rule.
10. **Viết static accessor cùng tên component:** Không đáp ứng instance method contract.
11. **Viết JavaBeans bridge rồi nghĩ accessor `name()` biến mất:** Nó vẫn hiện diện.
12. **Override accessor để trim nhưng không normalize field:** Generated equals/toString nhìn field raw.
13. **Dùng accessor để thay field final:** Không thể cập nhật record component field.
14. **Clone array chỉ ở constructor:** Getter vẫn có thể làm lộ internal array.
15. **Clone array chỉ ở getter:** Input alias vẫn có thể thay internal array.
16. **Coi `List.copyOf` deep-copy mọi element:** Nó chỉ bảo vệ cấu trúc List và giữ references elements.
17. **Dùng byte[] record component và kỳ vọng default equals theo contents:** Arrays thường được so theo reference.
18. **Dùng mutable record làm HashMap key không kiểm soát:** Nested mutable content có thể làm hash behavior bất ổn.
19. **Dựa `Introspector` để kết luận records không dùng được với mọi framework:** Framework-specific record support có thể tồn tại.
20. **Cho rằng mọi framework hiểu record components:** Cần kiểm tra version và config thực tế.
21. **Viết setter no-op cho record:** Làm sai contract của API.
22. **Đặt tên `boolean isReady` rồi nghĩ component tên `ready`:** Component thực sự là isReady.
23. **Coi getter prefix là type safety guarantee:** Property naming không validate null/format.
24. **Thay class bằng record mà không review clients gọi getX/setX:** Có thể phá source compatibility.
25. **Dùng `getClass()` thay record introspection APIs:** Record-specific metadata nằm ở Class.getRecordComponents.
26. **Không xét annotations target khi chuyển field/Bean sang record:** Có thể thay serializer mapping.
27. **Tạo expensive/side-effectful accessor dùng trong Comparator:** Kết quả có thể bất ổn.
28. **Nhầm tên record và type của component:** Accessor name lấy từ component identifier.
29. **Nhầm `getName()` của RecordComponent reflection với getter của object:** RecordComponent.getName() trả metadata String về component; không phải phương thức getName() trên record instance.
30. **Không phân biệt canonical constructor input và accessor output:** Nếu normalization/copying khác nhau, invariant có thể lệch.

## 26. Checklist thiết kế record API

1. Có thực sự cần record/value-like data type?
2. Component names đã rõ ràng và ổn định chưa?
3. Client nên gọi `name()` hay yêu cầu `getName()` compatibility?
4. Boolean component `active` có được hiểu đúng là `active()`?
5. Có legacy framework dùng Introspector/property conventions không?
6. Framework version có record-specific support không?
7. Có cần thêm JavaBeans bridge methods hoặc adapter DTO không?
8. Explicit accessor có public, đúng return type, không params/throws/generic không?
9. Custom accessor có làm result lệch raw component field không?
10. Nếu cần normalize, có làm ở canonical constructor trước khi lưu field không?
11. Có constructor validation cho null/blank/range không?
12. Components là primitive/immutable values hay mutable references?
13. Với mutable List, có snapshot và immutable elements phù hợp không?
14. Với arrays, có copy-on-input và copy-on-output không?
15. Generated equals/hashCode/toString có phù hợp component field semantics không?
16. Nếu component là array, có chấp nhận identity-based equality không?
17. Có cần method `withX()` để tạo record mới thay vì setter không?
18. Có dùng record accessor method references trong streams/comparators không?
19. Có đảm bảo accessors không có side effects ngoài ý muốn không?
20. Reflection code có dùng `RecordComponent` thay vì chỉ đoán getter names không?
21. Named modules có cần `requires java.desktop` cho JavaBeans APIs không?
22. Integration tests có kiểm tra serialization/deserialization với framework thực tế không?
23. Có tránh duplicate/conflicting property names khi thêm bridge getters không?
24. Có giữ record components và external schema mappings versioned không?
25. Có kiểm thử mutable alias isolation và hash-based collection behavior khi cần không?

## 27. Bài tập tự kiểm tra có đáp án

**Câu 1.** `record User(String name, int age)` sinh những accessor methods nào?

**Đáp án:** `public String name()` và `public int age()`.

**Câu 2.** Compiler có tự sinh `getName()` cho record không?

**Đáp án:** Không. Đó là JavaBeans-style getter convention, không phải record component accessor mặc định.

**Câu 3.** Với `record Flag(boolean active)`, accessor mặc định là gì?

**Đáp án:** `active()`, không phải `isActive()`.

**Câu 4.** `record Flag(boolean isActive)` có accessor gì?

**Đáp án:** `isActive()`, vì component identifier thực sự là isActive.

**Câu 5.** Record component field có public không?

**Đáp án:** Không; corresponding component field là private final, public accessor là cách đọc chuẩn.

**Câu 6.** Có thể viết explicit accessor không?

**Đáp án:** Có, nhưng phải public, instance, không tham số, đúng return type và không khai báo throws/type parameters.

**Câu 7.** `String name()` không ghi public trong record có hợp lệ không?

**Đáp án:** Không khi đó là accessor tường minh; phải public.

**Câu 8.** `Object name()` có thể thay accessor cho `String name` không?

**Đáp án:** Không, return type phải đúng String.

**Câu 9.** Có thể viết `name() throws IOException` làm component accessor không?

**Đáp án:** Không, explicit accessor không được có throws clause.

**Câu 10.** Thêm `getName()` có xóa `name()` không?

**Đáp án:** Không. Đó là extra method, implicit/explicit component accessor vẫn tồn tại.

**Câu 11.** JavaBeans getter có nhất thiết gắn với field cùng tên không?

**Đáp án:** Không; getter có thể tính property từ nhiều fields hoặc tính toán.

**Câu 12.** Getter-only JavaBeans property có bắt buộc setter không?

**Đáp án:** Không; read-only properties có thể tồn tại.

**Câu 13.** JavaBeans Introspector JDK 17 có tự hiểu bare record `name()` là `getName()` không?

**Đáp án:** Không theo convention chuẩn; dùng record component metadata hoặc bridge getter nếu library legacy cần.

**Câu 14.** Có API reflection nào lấy toàn bộ record components?

**Đáp án:** `Class.getRecordComponents()`, kết hợp `RecordComponent.getAccessor()`.

**Câu 15.** `RecordComponent.getAccessor()` trả thứ gì?

**Đáp án:** Một `java.lang.reflect.Method` đại diện accessor tương ứng component.

**Câu 16.** Record component accessor có dùng trong method reference không?

**Đáp án:** Có, ví dụ `User::name`.

**Câu 17.** Custom accessor trim String có tự làm generated equals so trimmed values không?

**Đáp án:** Không. Generated equals dựa trên component fields, không tự gọi custom accessor.

**Câu 18.** Nếu muốn toàn bộ record state normalized, nên xử lý ở đâu?

**Đáp án:** Trong canonical/compact constructor trước khi component fields được gán.

**Câu 19.** `toString()` sinh tự động có nhất thiết in output của custom accessor không?

**Đáp án:** Không; generated toString dựa trên component fields.

**Câu 20.** Record có thể có component là mutable List không?

**Đáp án:** Có, nhưng record không tự deep immutable; cần ownership/copy policy.

**Câu 21.** `List.copyOf(source)` có ngăn source.add sau construction đổi cấu trúc stored List không?

**Đáp án:** Có trong contract snapshot phù hợp, nhưng không deep-copy mutable elements.

**Câu 22.** Với component byte[], chỉ clone trong constructor có đủ không?

**Đáp án:** Không nếu accessor trả raw internal array; phải copy khi trả nếu cần ngăn mutation từ caller.

**Câu 23.** Chỉ clone array trong accessor có đủ không?

**Đáp án:** Không nếu constructor đã lưu raw input reference; caller có thể sửa qua input alias.

**Câu 24.** Default record equals so byte[] theo contents như Arrays.equals không?

**Đáp án:** Không. Array component equality thường theo reference identity.

**Câu 25.** `record P(int x)` có setter `setX` tự sinh không?

**Đáp án:** Không.

**Câu 26.** Cách “thay x” phù hợp value-style record là gì?

**Đáp án:** Tạo một record object mới với x mới, ví dụ `new P(9)` hoặc `withX` method trả instance mới.

**Câu 27.** Có thể dùng Bean getter bridge cho interface `LegacyNamed.getName` không?

**Đáp án:** Có. Record khai báo `getName()` gọi `name()`, còn component accessor vẫn tồn tại.

**Câu 28.** Một record có thể implement interface `NameBearing { String name(); }` qua implicit accessor không?

**Đáp án:** Có, nếu component accessor public với signature khớp interface.

**Câu 29.** `java.beans.Introspector` nằm trong module nào?

**Đáp án:** `java.desktop`; named modules dùng JavaBeans API cần module readability phù hợp.

**Câu 30.** Có nên giả định mọi JSON library đều tự xử lý records không?

**Đáp án:** Không; cần kiểm tra library version, annotations và native record support.

**Câu 31.** Tại sao không nên viết no-op setter trong record?

**Đáp án:** Vì client/framework có thể tưởng mutation thành công dù state không thay, làm contract sai.

**Câu 32.** Record accessor và JavaBeans getter đều là instance methods phải không?

**Đáp án:** Khi nói về regular getters/accessors trong bài, đúng; record accessor bị yêu cầu là instance method, JavaBeans property getter cũng thường là instance method.

**Câu 33.** Một boolean JavaBeans getter `isReady()` có tương đương record component `boolean ready` không?

**Đáp án:** Chỉ tương ứng về domain meaning nếu developer mapping. Compiler record vẫn sinh `ready()`; `isReady()` phải tự khai báo nếu cần.

**Câu 34.** Việc dùng `getName()` cho record có làm record thành mutable Bean không?

**Đáp án:** Không; thêm getter không thêm setter và không bỏ final component fields.

**Câu 35.** Điểm quan trọng nhất của bài?

**Đáp án:** **Record accessor = tên component kèm `()`, được Java tự tạo theo record contract; JavaBeans getter = naming convention `getX()/isX()`.** Muốn bridge phải tự thêm method hoặc dùng tooling record-aware; khi customize accessor phải giữ hiểu đúng raw fields, equality và ownership.

## 28. Bài tập thực hành

### Bài 1 — đọc từ record và JavaBean

Tạo `record Employee(String name, boolean active)` và `class EmployeeBean` với `getName()/isActive()`. Gọi đủ bốn methods hợp lệ; thử `employee.getName()` với record bare và phân tích compile error.

**Gợi ý:** Record header quyết định accessor names, không phải JavaBeans convention.

### Bài 2 — thêm bridge cho legacy interface

Tạo interface `LegacyAge { int getAge(); }` và record `Person(String name,int age) implements LegacyAge`. Viết `getAge()` gọi `age()`. Kiểm tra `Person::age` method reference vẫn hoạt động.

**Gợi ý:** Bridge là method bổ sung, không thay component accessor.

### Bài 3 — normalize ở accessor vs constructor

Tạo `record Raw(String id)` override `id()` để trim; tạo `record Clean(String id)` dùng compact constructor trim. So sánh `equals` và `toString` đối với inputs `" X "` và `"X"`.

**Gợi ý:** Generated equals/toString nhìn underlying component fields.

### Bài 4 — tránh mutable array leak

Tạo `record Payload(byte[] bytes)` clone trong constructor và clone trong accessor. Chứng minh sửa source array và sửa accessor result đều không làm payload thay.

**Gợi ý:** Copy-on-input và copy-on-output; cần review cả equality/hashCode cho array components.

### Bài 5 — reflection và framework compatibility

Dùng `Class.getRecordComponents()` để in component names/types/accessor method names. Dùng `Introspector` JDK 17 để so bare record và class có getX getters. Thêm bridge getters rồi chạy lại, đối chiếu property descriptors.

**Gợi ý:** Phân biệt JavaBeans API convention và record metadata; framework khác có thể dùng logic riêng.

## 29. Kết luận

**Accessor của record** được Java xác định trực tiếp từ **record component name**. Với `record User(String name, boolean active)`, phương thức đọc mặc định là `user.name()` và `user.active()`, **không phải `getName()` hay `isActive()`**. Các accessors này là public instance methods, có signatures gắn với component types, và có thể được khai báo tường minh trong phạm vi constraints của record language.

**JavaBeans getter** là một convention khác: `getName()`, `isActive()` và các method patterns liên quan để tools nhận biết read-only/read-write properties. Một record bare không tự sinh những names này; nếu cần hỗ trợ clients cũ, có thể thêm bridge getters hoặc chọn mapper hiểu record components qua `Class.getRecordComponents()` và `RecordComponent.getAccessor()`.

Đừng quên rằng **record component field là final nhưng referent có thể mutable**. Nếu tự viết accessor để normalize hoặc defensive-copy, phải tính đến canonical constructor và generated `equals/hashCode/toString` vốn dựa trên component fields chứ không tự gọi transformed accessor. Với List/array, kiểm soát ownership bằng immutable representation hoặc copy-on-input/output phù hợp.

Hiểu đúng **component declaration → public accessor `component()`**, đồng thời phân biệt **JavaBeans naming → getX/isX**, sẽ giúp thiết kế records rõ nghĩa, dùng method references và reflection đúng, và tích hợp framework an toàn mà không vô tình phá value semantics.
