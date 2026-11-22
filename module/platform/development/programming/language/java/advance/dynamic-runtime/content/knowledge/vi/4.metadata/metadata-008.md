# 4.8 Khám phá RecordComponent và liên hệ với accessor, constructor của record

Một `record` trong Java mô tả dữ liệu bằng danh sách **record components** ngay trong phần khai báo: `record Point(int x, int y) {}`. Khi hệ thống chỉ biết `Class<?>` tại thời điểm chạy, Reflection có thể khôi phục danh sách component và tìm đúng **accessor** cũng như **canonical constructor**. Đây là nền tảng của bộ đọc metadata, mapper, serializer, công cụ kiểm thử, plugin và dependency injection có hỗ trợ record.

Điểm quan trọng: một record component là **thành phần khai báo trong record header**, không đồng nhất với `Field`, `Method` hay tham số constructor. Tuy nhiên, mỗi component liên hệ với một field `private final`, một accessor không tham số và một vị trí tham số của canonical constructor. Java cung cấp API `java.lang.reflect.RecordComponent` để khám phá trực tiếp mối liên hệ đó.

**Sau bài này**, bạn có thể:

- Kiểm tra `Class.isRecord()` và lấy các `RecordComponent` theo đúng thứ tự khai báo.
- Phân biệt `getName()`, `getType()`, `getGenericType()`, `getAnnotatedType()` và `getAccessor()`.
- Dùng `RecordComponent.getAccessor()` để đọc giá trị của một đối tượng record với quy tắc truy cập Reflection thông thường.
- Xác định canonical constructor từ **đúng danh sách kiểu component theo thứ tự record header**, kể cả với compact constructor và record generic.
- Phân biệt annotation trên component với annotation trên accessor, field và tham số constructor.
- Thiết kế đoạn mã khám phá record đủ an toàn khi gặp lớp không phải record, record rỗng, component mảng, generic, overload và ràng buộc truy cập module.

Các API này dùng ổn định từ **Java 16**; ví dụ dưới đây biên dịch với **Java 17+**.

## 1. Record được tổ chức như thế nào?

Xét khai báo:

```java
public record Book(String title, int pages) {}
```

Đây là đoạn khai báo minh họa. Java gắn khái niệm sau với record:

| Thành phần | Ví dụ tương ứng | Ý nghĩa |
| --- | --- | --- |
| Record header | `String title, int pages` | Hai record components, có thứ tự `title` trước `pages` |
| Component field | `private final String title`, `private final int pages` | Field thực sự lưu trạng thái; compiler sinh ngầm |
| Accessor | `public String title()`, `public int pages()` | Trả giá trị component; có thể do compiler sinh hoặc người viết khai báo rõ |
| Canonical constructor | `Book(String title, int pages)` | Khởi tạo toàn bộ component theo đúng danh sách và thứ tự header |
| Phương thức chuẩn | `equals`, `hashCode`, `toString` | Có triển khai mặc định dựa trên component fields, trừ trường hợp khai báo lại hợp lệ |

Lớp record kế thừa `java.lang.Record`, không kế thừa thêm một lớp ứng dụng khác; record ngầm là `final`. Các instance component fields là `private final` và chỉ được khởi tạo qua quá trình tạo record. **Final ở đây không đồng nghĩa bất biến sâu**: nếu component là `List` hay mảng có thể thay đổi, bản thân đối tượng tham chiếu vẫn có thể bị sửa trừ khi thiết kế phòng vệ.

Một record được phép khai báo thêm constructor phụ, static field, static method và instance method, nhưng **không được khai báo instance field bổ sung**. Cần nhớ rằng `Book(String title, int pages)` là canonical constructor, còn `Book(String title)` (nếu có) chỉ là constructor phụ và phải ủy quyền đến constructor khác của record bằng `this(...)`.

### 1.1. Từ record header sang mô hình Reflection

```text
record Book(String title, int pages)
      |
      +-- Class<Book>.getRecordComponents()
      |     +-- RecordComponent "title" : String
      |     |       +-- getAccessor() -> Method title()
      |     +-- RecordComponent "pages" : int
      |             +-- getAccessor() -> Method pages()
      |
      +-- getDeclaredConstructor(String.class, int.class)
            -> canonical constructor theo đúng thứ tự component
```

`Class.getRecordComponents()` được thiết kế cho đúng mục tiêu trên. Đừng dùng `getDeclaredFields()` rồi giả định đó chính là record header: field và component là hai khái niệm riêng, field có thể bao gồm trường `static`, và thứ tự trả về từ các API liệt kê field không phải hợp đồng để suy ra thứ tự component.

## 2. API RecordComponent cần biết

| API | Trả về | Cách sử dụng |
| --- | --- | --- |
| `Class.isRecord()` | `boolean` | Phân nhánh khi xử lý một `Class<?>` |
| `Class.getRecordComponents()` | `RecordComponent[]` hoặc `null` | Danh sách component theo **thứ tự khai báo**; `null` nếu không phải record |
| `RecordComponent.getName()` | `String` | Tên đúng trong header, ví dụ `title` |
| `getType()` | `Class<?>` | Kiểu runtime đã xóa generic; dùng để tìm constructor |
| `getGenericType()` | `Type` | Kiểu khai báo mang thông tin generic, ví dụ `List<String>` |
| `getGenericSignature()` | `String` hoặc `null` | Chữ ký generic theo định dạng JVM khi có; thông thường dùng `Type` sẽ thuận tiện hơn |
| `getAnnotatedType()` | `AnnotatedType` | Thông tin annotation tại **vị trí sử dụng kiểu** của component |
| `getAccessor()` | `Method` | Accessor không tham số, cùng tên component, kiểu trả về khớp kiểu component |
| `getDeclaringRecord()` | `Class<?>` | Record khai báo component đó |
| `getAnnotation(A.class)` | `A` hoặc `null` | Annotation có thể đọc trực tiếp trên **component**, theo `@Target` và `@Retention` |
| `getDeclaredAnnotations()` / `getAnnotations()` | `Annotation[]` | Khám phá annotation trực tiếp trên component |

**Hai trường hợp biên đặc biệt:**

- `String.class.isRecord()` là `false` và `String.class.getRecordComponents()` là **`null`**. Không dùng vòng lặp ngay nếu chưa kiểm tra.
- Với `record Empty() {}`, `isRecord()` là `true` và `getRecordComponents()` là **mảng độ dài 0**, không phải `null`. Canonical constructor khi đó không nhận tham số.

Một record component không có `getValue(record)`. `getAccessor()` trả về một đối tượng `Method`; muốn đọc giá trị, ta dùng `accessor.invoke(recordInstance)`, qua đó vẫn phải tuân thủ quyền truy cập và ngoại lệ của Reflection.

## 3. Quan hệ giữa component và accessor

Với `record Account(String id, int level) {}`, tên accessor lần lượt là `id()` và `level()`. Chúng **không theo quy tắc JavaBeans** kiểu `getId()` hoặc `getLevel()`. Cách đáng tin là lấy `RecordComponent.getAccessor()` thay vì tự suy luận tên hoặc tìm một getter bắt đầu bằng “get”.

### 3.1. Accessor được sinh ngầm hoặc khai báo tường minh

```java
record User(String username) {
    @Override
    public String username() {
        return username;
    }
}
```

Đây là đoạn minh họa: accessor được khai báo rõ, có cùng tên và kiểu trả về của component. Khi gọi `User.class.getRecordComponents()[0].getAccessor()`, Reflection vẫn tìm đúng `Method username()`. Nếu không viết accessor, compiler sinh accessor tương đương trả về component field.

**Không được giả định accessor tùy biến phải trả lại field không đổi trong mọi chương trình**, nhưng cần thiết kế nhất quán với hợp đồng của record: việc tạo một bản sao qua canonical constructor từ giá trị của các accessor phải duy trì ý nghĩa `equals`. Ví dụ, nếu accessor tự ý trả về giá trị khác với trạng thái mà `equals` dùng, bất biến ngữ nghĩa mong đợi của record có thể bị phá vỡ. Chuẩn hóa dữ liệu ở constructor rồi để accessor trả trạng thái đã chuẩn hóa thường dễ bảo đảm hơn.

### 3.2. Đọc giá trị bằng Reflection

```java
RecordComponent component = Account.class.getRecordComponents()[0];
Method accessor = component.getAccessor();
String id = (String) accessor.invoke(new Account("A01", 2));
```

Đoạn minh họa cần các import `java.lang.reflect.RecordComponent` và `java.lang.reflect.Method`. `invoke` dùng đối tượng record làm receiver và **không có đối số phương thức**, vì accessor không nhận tham số. Phương thức do Reflection trả về có kiểu trả về đúng với `component.getType()`; kiểu primitive khi trả qua `Method.invoke` được boxed, ví dụ giá trị `int` trở thành `Integer` trong kết quả `Object`.

Nếu một accessor tự ném ngoại lệ, `Method.invoke` sẽ bao ngoại lệ đó trong `InvocationTargetException`. Nếu record không hiển thị cho caller do phạm vi truy cập hoặc module, lời gọi có thể gặp `IllegalAccessException` ngay cả khi đã lấy được metadata; không nên mặc định mọi `getAccessor()` đều gọi được từ mọi module.

## 4. Canonical constructor: xác định từ đúng kiểu component

Canonical constructor có danh sách tham số **cùng số lượng, cùng kiểu, cùng thứ tự** với record components. Với `record Book(String title, int pages)`, chữ ký canonical là `(String, int)`; với `record Box<T>(T value)`, ở Reflection sau xóa kiểu, tham số tương ứng thường là `Object` nếu `T` không có bound hạn chế.

Vì `getRecordComponents()` trả về đúng thứ tự header, ta có thể viết:

```java
RecordComponent[] components = recordClass.getRecordComponents();
Class<?>[] parameterTypes = Arrays.stream(components)
        .map(RecordComponent::getType)
        .toArray(Class<?>[]::new);
Constructor<?> canonical = recordClass.getDeclaredConstructor(parameterTypes);
```

Đây là đoạn minh họa với `recordClass` đã được xác minh `isRecord()==true` và các import thích hợp (`Arrays`, `RecordComponent`, `Constructor`). Dùng `getDeclaredConstructor` để tìm theo **chữ ký chính xác**; không chọn constructor “đầu tiên” trong mảng `getDeclaredConstructors()` hoặc mặc định constructor ít tham số nhất là canonical.

| Kiểu constructor | Ví dụ | Có phải canonical? |
| --- | --- | --- |
| Sinh ngầm từ header | `record Point(int x, int y) {}` | Có: `Point(int, int)` |
| Normal canonical tường minh | `public Point(int x, int y) { this.x=x; this.y=y; }` trong record `Point` | Có nếu thỏa các quy định của canonical constructor |
| Compact canonical | `public Point { if (x < 0) throw new IllegalArgumentException(); }` | Có: chữ ký vẫn là `Point(int, int)` |
| Constructor phụ | `public Point() { this(0, 0); }` | Không: `Point()` chỉ ủy quyền tới canonical constructor |

### 4.1. Compact constructor không làm thay đổi chữ ký

```java
public record Product(String code, int quantity) {
    public Product {
        code = code.trim();
        if (quantity < 0) throw new IllegalArgumentException("quantity");
    }
}
```

Trong compact canonical constructor, tham số được suy ra từ record header; body có thể kiểm tra và chuẩn hóa tham số. Sau body, các field được gán từ các giá trị tham số (đã cập nhật). Reflection vẫn tìm qua `getDeclaredConstructor(String.class, int.class)`. Gọi `canonical.newInstance("  P1  ", 2)` sẽ áp dụng cùng kiểm tra/chuẩn hóa như gọi trực tiếp `new Product("  P1  ", 2)`.

Nếu constructor ném `IllegalArgumentException` bên trong body, `Constructor.newInstance` thường ném `InvocationTargetException` với `getCause()` là lỗi đó. Hãy phân biệt với `IllegalArgumentException` phát sinh **trước khi vào constructor** vì số lượng/kiểu đối số không hợp lệ.

### 4.2. Không đánh đồng constructor phụ với canonical

```java
record Ticket(String code, int price) {
    Ticket(String code) { this(code, 0); }
}
```

Đoạn minh họa trên có canonical constructor `Ticket(String, int)` do compiler sinh, đồng thời có constructor phụ `Ticket(String)`. Hai constructor đều có thể xuất hiện trong `getDeclaredConstructors()`; thứ tự mảng không được dùng để định danh canonical.

**Một record chỉ có một canonical constructor**, dù bạn có thể viết thêm nhiều constructor phụ. Với constructor canonical có giới hạn truy cập, Reflection vẫn tìm thấy bằng `getDeclaredConstructor` nhưng `newInstance` phải tuân thủ visibility và module; giữ nguyên chính sách truy cập là lựa chọn an toàn cho hệ thống động.

## 5. Ví dụ Java 17+ chạy được: khám phá component, accessor và constructor

Tạo tệp **`RecordMetadataDemo.java`** chứa chương trình dưới đây. Nó có một record `Article` dùng compact canonical constructor, một constructor phụ, một accessor được khai báo tường minh và annotation chỉ áp dụng cho record component; có thêm record generic `Box<T>` để quan sát type erasure.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RecordMetadataDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface Caption { String value(); }

    public record Article(@Caption("primary title") String title,
                          List<String> tags, int pages) {
        public Article {
            title = Objects.requireNonNull(title).trim();
            tags = List.copyOf(tags);
            if (pages < 0) throw new IllegalArgumentException("pages");
        }

        public Article(String title) {
            this(title, List.of(), 0);
        }

        @Override
        public String title() { return title; }
    }

    public record Box<T>(T value, List<T> history) {}

    public static void main(String[] args) throws Exception {
        Class<Article> recordClass = Article.class;
        System.out.println("isRecord=" + recordClass.isRecord());
        System.out.println("ordinaryIsRecord=" + String.class.isRecord());
        System.out.println("ordinaryComponentsNull=" + (String.class.getRecordComponents() == null));

        RecordComponent[] components = recordClass.getRecordComponents();
        System.out.println("componentCount=" + components.length);
        for (RecordComponent rc : components) {
            System.out.println(rc.getName() + " | raw=" + rc.getType().getTypeName()
                    + " | generic=" + rc.getGenericType().getTypeName()
                    + " | accessor=" + rc.getAccessor().getName() + "()");
        }
        Class<?>[] types = Arrays.stream(components)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);
        Constructor<Article> canonical = recordClass.getDeclaredConstructor(types);
        System.out.println("canonicalParameterCount=" + canonical.getParameterCount());
        System.out.println("allConstructors=" + recordClass.getDeclaredConstructors().length);

        Article article = canonical.newInstance("  Java  ", List.of("reflection", "metadata"), 12);
        for (RecordComponent rc : components) {
            System.out.println("read " + rc.getName() + "=" + rc.getAccessor().invoke(article));
        }
        System.out.println("caption=" + components[0].getAnnotation(Caption.class).value());
        System.out.println("declaringRecord=" + components[0].getDeclaringRecord().getSimpleName());
        System.out.println("accessorCaption="
                + (components[0].getAccessor().getAnnotation(Caption.class) != null));

        RecordComponent generic = Box.class.getRecordComponents()[0];
        System.out.println("genericRaw=" + generic.getType().getTypeName());
        System.out.println("genericType=" + generic.getGenericType().getTypeName());
        System.out.println("genericSignature=" + generic.getGenericSignature());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 RecordMetadataDemo.java
java RecordMetadataDemo
```

Kết quả `stdout` trên JDK 17+:

```text
isRecord=true
ordinaryIsRecord=false
ordinaryComponentsNull=true
componentCount=3
title | raw=java.lang.String | generic=java.lang.String | accessor=title()
tags | raw=java.util.List | generic=java.util.List<java.lang.String> | accessor=tags()
pages | raw=int | generic=int | accessor=pages()
canonicalParameterCount=3
allConstructors=2
read title=Java
read tags=[reflection, metadata]
read pages=12
caption=primary title
declaringRecord=Article
accessorCaption=false
genericRaw=java.lang.Object
genericType=T
genericSignature=TT;
```

**Những kết quả cần hiểu:**

1. `Article` là record; `String` không phải. `getRecordComponents()` của `String` trả `null` nên phải kiểm tra trước khi duyệt.
2. Thứ tự component là `title` → `tags` → `pages`, đúng thứ tự header. `getType()` của `tags` là `List.class`, còn `getGenericType()` giữ được thông tin `List<String>`.
3. Canonical constructor có đúng **3 tham số**, dù `Article` có **2 constructor tổng cộng** (canonical và constructor phụ).
4. `Article` được tạo qua Reflection vẫn chạy compact constructor: `"  Java  "` được trim thành `"Java"` và `tags` được copy thành danh sách không thể sửa cấu trúc.
5. `rc.getAccessor().invoke(article)` đọc mỗi component bằng đúng accessor, kể cả `title()` được khai báo tường minh.
6. `Caption` chỉ được phép gắn lên `RECORD_COMPONENT`, nên `getAnnotation` trên component thấy annotation, còn accessor không mang annotation đó.
7. Với `Box<T>`, kiểu runtime sau erasure của `T` là `Object`, nhưng `getGenericType()` cho biết đây là type variable `T`; chữ ký generic thô là `TT;`.

Ví dụ này dùng `public` cho các nested record và chạy từ chính lớp bao nên không cần phá kiểm tra quyền truy cập.

## 6. Khám phá generic và annotation cho đúng nơi

### 6.1. Raw type và generic type

`RecordComponent.getType()` trả `Class<?>` đã xóa thông tin tham số kiểu. `getGenericType()` trả `Type`, có thể là:

- `Class<?>` cho `String`, `int` hoặc kiểu thông thường không generic.
- `ParameterizedType` cho kiểu như `List<String>`.
- `TypeVariable<?>` cho `T` ở `record Box<T>(T value)`.
- `GenericArrayType` khi kiểu mảng có thành phần là type variable hoặc generic, tùy khai báo.

Để phân tích chi tiết, kiểm tra `instanceof ParameterizedType` hay `instanceof TypeVariable<?>`. `getGenericSignature()` trả ký pháp signature của JVM (nếu có); **không nên đem chuỗi này làm tên lớp cho `Class.forName` hoặc coi nó là JVM field descriptor**.

Quan trọng: dù metadata giữ `List<String>`, một `Constructor` khi được tìm bằng Reflection vẫn nhận `List.class` làm kiểu tham số cho vị trí ấy. Ví dụ:

```java
RecordComponent component = Article.class.getRecordComponents()[1];
System.out.println(component.getType() == List.class); // true
```

Đoạn trên tham chiếu lớp `Article` của chương trình đầy đủ. Khi tạo mapper, dùng kiểu runtime `getType()` để chọn constructor, còn `getGenericType()` để giải thích hay ràng buộc kiểu phần tử cho serializer.

### 6.2. Annotation trên component khác annotation trên accessor

`RecordComponent` triển khai `AnnotatedElement`. Tuy vậy, vị trí của một annotation được quyết định bởi `@Target`:

- `@Target(RECORD_COMPONENT)` cho phép xuất hiện trực tiếp trên record component.
- `@Target(METHOD)` dùng trên phương thức; annotation ở record header có thể được **phân phối** lên accessor được sinh ngầm nếu annotation hợp lệ cho `METHOD`.
- `@Target(FIELD)` có thể đưa annotation áp dụng vào field component; `@Target(PARAMETER)` có thể ảnh hưởng đến tham số canonical constructor theo quy định về khai báo ngầm.
- Nếu accessor hoặc normal canonical constructor được **khai báo tường minh**, quy tắc phân phối annotation khác với thành viên được sinh; không thể suy đoán một annotation chắc chắn xuất hiện ở tất cả vị trí.

Vì vậy, hãy đọc annotation ở **đúng đối tượng Reflection**: `rc.getAnnotation(...)` cho record component, `rc.getAccessor().getAnnotation(...)` cho accessor, `field.getAnnotation(...)` cho field, hay `constructor.getParameters()[i].getAnnotation(...)` cho tham số constructor. Không đánh đồng bốn nguồn metadata này.

Annotation tại *type use* còn là chuyện khác. Chẳng hạn:

```java
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface SensitiveType {}

record Catalog(java.util.List<@SensitiveType String> names) {}
```

Đây là khai báo minh họa với các import `ElementType`, `Target`, `Retention`, `RetentionPolicy`. Annotation gắn với **kiểu `String` nằm trong `List<...>`**. Để khám phá, dùng `RecordComponent.getAnnotatedType()`, kiểm tra `AnnotatedParameterizedType` rồi xem `getAnnotatedActualTypeArguments()`; chỉ gọi `getAnnotations()` trên bản thân `RecordComponent` có thể không thấy thông tin *type-use* đó.

### 6.3. Annotation ở compile-time có thể không hiện khi chạy

Annotation retention là bộ lọc khác với target: `@Retention(RUNTIME)` mới bảo đảm metadata annotation tương ứng có thể đọc qua Reflection ở runtime. Annotation `SOURCE` bị loại trong quá trình biên dịch; `CLASS` có thể nằm trong class file nhưng không nhất thiết hiển thị qua các API Reflection thông thường. Với các framework đọc annotation, cần kiểm tra cả `@Target` lẫn `@Retention`.

## 7. Xây bộ phân tích record metadata trong hệ thống động

Giả sử bạn xây bộ chuyển từ JSON/Map sang record hoặc bộ kiểm thử chỉ nhận `Class<?>` tại runtime. Quy trình đáng tin:

1. **Nhận diện loại:** `if (!type.isRecord())` thì từ chối hoặc chuyển nhánh xử lý class thường. Đừng suy ra class là record chỉ vì có các method không tham số.
2. **Lấy danh sách component:** `RecordComponent[] components = type.getRecordComponents()`. Đây là danh sách có thứ tự ổn định theo header; record rỗng vẫn cho mảng không null.
3. **Tạo schema:** cho mỗi component, ghi `name`, `type`, `genericType`, annotation cần thiết và `accessor`. Dùng `getDeclaringRecord()` để xác nhận nơi khai báo.
4. **Đọc một instance:** kiểm tra instance có đúng kiểu record; gọi từng `getAccessor().invoke(instance)`. Tránh truy cập private component fields khi accessor đáp ứng yêu cầu.
5. **Chuẩn bị giá trị theo đúng thứ tự:** ánh xạ dữ liệu đầu vào theo `component.getName()` nhưng sắp danh sách đối số constructor bằng **thứ tự của mảng components**. Đừng dựa vào thứ tự key ngẫu nhiên của Map hoặc thứ tự getDeclaredFields.
6. **Tìm canonical constructor:** tạo `Class<?>[]` bằng từng `component.getType()`, sau đó `getDeclaredConstructor(types)`. Không chọn theo tên, số parameter bất kỳ hay index của `getDeclaredConstructors()`.
7. **Gọi constructor:** tạo `Object[] arguments` có một phần tử cho mỗi component và gọi `canonical.newInstance(arguments)`. Kiểm tra primitive, null, mảng, generic, quyền truy cập, ngoại lệ phát sinh từ validation và độ tin cậy của dữ liệu trước khi gọi.
8. **Báo lỗi có ngữ cảnh:** khi thiếu key hoặc giá trị không hợp lệ, báo tên component, kiểu khai báo và vị trí; nếu `InvocationTargetException`, xem `getCause()` để phân biệt lỗi bên trong canonical constructor.

### 7.1. Vì sao không khởi tạo bằng no-arg constructor rồi set field?

Record không có no-arg constructor mặc định, trừ trường hợp canonical constructor có **0 component** hoặc lập trình viên viết constructor phụ phù hợp. Các component fields là `private final`, và việc sửa chúng phản chiếu sau khi xây đối tượng không phải cơ chế xây record đúng chuẩn. Mapper nên thu thập/validate đủ dữ liệu rồi **gọi canonical constructor**. Cách này giữ các ràng buộc trong compact/normal canonical constructor và tránh phụ thuộc vào thủ thuật sửa final fields.

### 7.2. Ánh xạ kiểu nguyên thủy, mảng, varargs

| Header component | `getType()` | Tham số canonical constructor |
| --- | --- | --- |
| `int count` | `int.class` | Một `int`; Reflection có thể unbox giá trị wrapper tương thích |
| `String name` | `String.class` | Một tham chiếu `String` |
| `String[] labels` | `String[].class` | Một đối số `String[]` |
| `List<String> tags` | `List.class` | Một đối số `List`, thông tin generic cần kiểm tra riêng |
| `String... labels` (component cuối) | `String[].class` | Một đối số mảng `String[]`; canonical constructor có cờ varargs |

Với `record Event(String name, String... labels) {}`, `getRecordComponents()` trả hai component; component `labels` có kiểu runtime `String[]`. Constructor canonical tìm bằng `getDeclaredConstructor(String.class, String[].class)` và `Constructor.isVarArgs()` trả `true`. **Reflection không tự trải hoặc thu gọn các giá trị varargs theo ý bạn**: hãy chuẩn bị danh sách `Object[]` chứa đúng một phần tử `String[]` ở vị trí cuối. Ví dụ:

```java
Constructor<Event> ctor = Event.class.getDeclaredConstructor(
        String.class, String[].class);
Event event = ctor.newInstance(new Object[] {
        "created", new String[] {"audit", "async"}
});
```

Đây là đoạn minh họa, giả định record `Event` đã được khai báo; `new Object[]{...}` là **danh sách hai tham số của constructor**, trong đó phần tử thứ hai là **một mảng**. Nếu truyền hai chuỗi thay cho component mảng, `newInstance` không tự đóng gói chúng thành `String[]`.

## 8. Những trường hợp biên và lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `getRecordComponents() == null` | `Class<?>` không phải record | Kiểm tra `isRecord()` rồi quyết định nhánh khác |
| `getRecordComponents().length == 0` | Record hợp lệ với header rỗng | Tìm canonical constructor không tham số |
| Không tìm thấy constructor | Dùng sai thứ tự/kiểu component, dùng `List<String>` như `Class<?>`, hoặc chỉ lấy một phần components | Dùng toàn bộ `getType()` theo thứ tự header |
| Lấy constructor phụ nhầm | Chọn phần tử đầu của `getDeclaredConstructors()` | Dùng `getDeclaredConstructor(componentTypes)` |
| `IllegalArgumentException` tại `newInstance` | Sai số đối số hoặc kiểu, ví dụ truyền `Object[]` thay `String[]` ở một component | Xây `Object[]` đúng số component và giá trị thực tế |
| `InvocationTargetException` tại `newInstance` | Constructor thực sự chạy rồi ném lỗi validation hoặc lỗi logic | Đọc `getCause()` và xử lý theo nghiệp vụ |
| `IllegalAccessException` / `InaccessibleObjectException` | Caller không có quyền truy cập record/constructor/accessor; hạn chế module | Sửa API visibility/module exports/opens đúng chính sách |
| Đọc annotation ở component nhưng không thấy trên getter | `@Target` hoặc accessor explicit làm thay đổi nơi annotation xuất hiện | Kiểm tra vị trí khai báo và đúng `AnnotatedElement` |
| `getType()` là `Object` nhưng khai báo `T` | Type erasure | Dùng `getGenericType()` để lấy metadata generic |
| Serializer nhìn thấy `List` nhưng không biết phần tử | Chỉ dùng `getType()` | Phân tích `ParameterizedType` hoặc `AnnotatedType` khi cần |
| Dữ liệu record bị đổi sau khởi tạo | Thành phần tham chiếu một đối tượng mutable, như mảng hoặc collection mutable | Defensive copy và kiểm soát cấp độ bất biến mong muốn |
| Accessor cho kết quả khác kỳ vọng của equals | Custom accessor làm biến đổi giá trị so với field lưu trữ | Thiết kế constructor/accessor nhất quán với giá trị component |

**Phạm vi dữ liệu và giới hạn:** Reflection khám phá **cấu trúc đã biên dịch**, không truy xuất được mọi biểu thức nguồn Java. Với generic, type variable và type-use annotation, đọc thông tin từ `Type` và `AnnotatedType`; đừng dùng tên kiểu dạng chuỗi để đoán mọi loại metadata. Với record thuộc module khác, việc đọc metadata không tự động cấp quyền gọi constructor không công khai.

### 8.1. Khác nhau giữa record và JavaBeans

| Tiêu chí | Record | JavaBeans class thông thường |
| --- | --- | --- |
| Mô tả state | Header components công khai về mặt metadata | Thuộc tính thường suy ra từ getter/setter/field theo quy ước |
| Getter | `name()`, không có tiền tố `get` | Thường `getName()` / `isActive()` |
| Khởi tạo chính | Canonical constructor với toàn bộ component | Có thể no-arg constructor và setter |
| Ghi trạng thái sau tạo | Component fields `private final`, không có setter component mặc định | Tùy thiết kế, có thể setter hoặc mutable field |
| Reflection hữu ích | `Class.getRecordComponents()`, `RecordComponent.getAccessor()` | `java.beans.Introspector` (nếu dùng JavaBeans), `Method`, `Field` |

**Đừng biến record thành JavaBeans bằng cách bắt nó phải có `getX()` hay no-arg constructor.** Các framework cần nhận diện record và gọi canonical constructor phù hợp thay vì bỏ qua cấu trúc header.

## 9. Bài tập tự kiểm tra

**Bài 1.** Cho `record Pair(String key, long value) {}`. Cần truyền kiểu nào vào `Pair.class.getDeclaredConstructor(...)`? 

**Đáp án:** `String.class, long.class` theo đúng thứ tự; `Long.class` không thay thế được `long.class` khi tra cứu chữ ký constructor.

**Bài 2.** `record Empty() {}`. `Empty.class.getRecordComponents()` trả về gì? 

**Đáp án:** Mảng độ dài 0; `Empty.class.getDeclaredConstructor()` tìm canonical constructor không tham số.

**Bài 3.** `record Envelope<T>(T payload) {}`. Với component `payload` không có bound đặc biệt, `getType()` và `getGenericType()` khác gì nhau?

**Đáp án:** `getType() == Object.class`; `getGenericType()` trả về `TypeVariable` đại diện `T`. Để tìm canonical constructor trên lớp runtime, dùng `Object.class`.

**Bài 4.** Một record có constructor `R(String name)` và canonical constructor `R(String name, int version)`. Có thể lấy canonical bằng `getDeclaredConstructors()[0]` không?

**Đáp án:** Không; thứ tự mảng không bảo đảm. Dùng danh sách `RecordComponent.getType()` để lấy `String.class, int.class` và gọi `getDeclaredConstructor`.

**Bài 5.** `RecordComponent.getAnnotation(Tag.class)` có giá trị nhưng `component.getAccessor().getAnnotation(Tag.class)` là `null`. Có mâu thuẫn không?

**Đáp án:** Không. Component, accessor, field và constructor parameter có các vị trí annotation khác nhau; kiểm tra `@Target`, `@Retention` và cách accessor được khai báo.

## Tài liệu chuẩn

- JDK 17, `java.lang.Class` — `isRecord()` và `getRecordComponents()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- JDK 17, `java.lang.reflect.RecordComponent` — `getAccessor()`, `getType()`, `getGenericType()`, annotation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html
- JDK 17, `java.lang.reflect.Constructor` — `newInstance` và lỗi Reflection: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
- Java Language Specification 17, `8.10` (*Record Classes*) — các component, thành viên và canonical/compact constructor: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
- JDK 17, `java.lang.Record` — hợp đồng nền tảng của record: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html

**Ghi nhớ:** `RecordComponent` là metadata của **header**, `getAccessor()` nối component tới phương thức đọc giá trị, còn **danh sách `getType()` theo thứ tự header** là cách chắc chắn để tìm canonical constructor. Khi phản chiếu, hãy phân biệt kiểu runtime với generic type, annotation component với annotation ở thành viên khác, và lỗi đóng gói tham số với lỗi từ chính constructor.
