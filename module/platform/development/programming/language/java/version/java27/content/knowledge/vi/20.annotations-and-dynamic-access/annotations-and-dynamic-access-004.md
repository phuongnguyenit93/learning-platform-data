# Reflection với class, record component và generic metadata

Trong Java 27, **reflection** là khả năng khám phá cấu trúc của kiểu dữ liệu và, khi được phép, tương tác với thành phần của kiểu đó **tại thời điểm chạy**. Nhờ reflection, một framework có thể đọc tên và kiểu của các thuộc tính, phát hiện annotation, xác định chữ ký method, lấy thông tin generic và xây dựng cơ chế ánh xạ dữ liệu mà không cần biết trước mọi lớp lúc viết mã nguồn.

Chủ đề này đặc biệt hữu ích khi làm việc với **record**. Một record khai báo các *component* ngay trong phần đầu, ví dụ **record Product(String sku, List<String> tags)**. Java cung cấp API riêng **java.lang.reflect.RecordComponent** để truy vấn đúng mô hình record, thay vì cố suy ra cấu trúc đó từ các field thông thường.

Bài học sử dụng các API chính thức vẫn áp dụng trong Java 27: **Class**, **RecordComponent**, **Field**, **Method**, **Constructor**, **Type**, **ParameterizedType**, **TypeVariable**, **WildcardType**, **GenericArrayType**, **AnnotatedType**, **AnnotatedParameterizedType** và annotation runtime. Đồng thời, bài giải thích giới hạn **type erasure** và **strong encapsulation** của Java Platform Module System (JPMS).

## 1. Khi nào cần reflection?

Trong Java, cách truy cập thông thường là **kiểm tra kiểu tại lúc biên dịch**:

~~~java
record Customer(String id, String name) {}

Customer customer = new Customer("C-01", "Lan");

System.out.println(customer.name());
~~~

Trình biên dịch biết **Customer** có accessor **name()**, nên sẽ phát hiện lỗi nếu bạn gọi một method không tồn tại.

Reflection làm việc với mô tả kiểu và thành phần của nó:

~~~java
Class<?> type = Customer.class;

System.out.println(type.getName());
System.out.println(type.isRecord());
~~~

Kết quả về mặt ý nghĩa:

~~~text
Customer
true
~~~

Đối tượng **Class<?>** mô tả một kiểu; nó không phải là instance của record **Customer**. Khi dùng reflection để gọi một accessor hoặc constructor, ta đang chuyển từ **truy cập tĩnh** sang **truy cập động**.

Các ứng dụng phù hợp:

- Framework ánh xạ dữ liệu: đọc record component để map JSON, cơ sở dữ liệu hoặc thông điệp.
- Validation: đọc annotation và kiểm tra ràng buộc trên kiểu hoặc component.
- Dependency injection: khám phá constructor và parameter metadata.
- Công cụ lập tài liệu/schema: mô tả cấu trúc kiểu và generic types.
- Hệ thống plugin có hợp đồng rõ ràng: tìm những lớp, method được cấu hình cho phép.

**Không nên mặc định dùng reflection cho logic nghiệp vụ đơn giản.** Nếu kiểu đã biết tại thời điểm biên dịch, gọi method hoặc accessor trực tiếp thường dễ đọc, dễ kiểm tra và dễ refactor hơn.

## 2. Class<?>: điểm xuất phát để đọc metadata

Mỗi kiểu Java được biểu diễn ở runtime bởi một đối tượng **Class**.

Ba cách lấy **Class**:

~~~java
Class<String> fromLiteral = String.class;

String value = "Java 27";
Class<?> fromInstance = value.getClass();

Class<?> fromName = Class.forName("java.lang.String");

System.out.println(fromLiteral == fromInstance); // true
System.out.println(fromLiteral == fromName);     // true
~~~

| Cách lấy | Đặc điểm |
|---|---|
| **SomeType.class** | Kiểu đã biết lúc biên dịch; kiểm tra tên kiểu sớm |
| **object.getClass()** | Lấy lớp runtime thực tế của một instance; không dùng trực tiếp với **null** |
| **Class.forName("...")** | Tìm lớp theo tên nhị phân; có thể ném **ClassNotFoundException** và bản một tham số có thể kích hoạt khởi tạo lớp |

Nếu tên lớp đến từ cấu hình hay dữ liệu người dùng, **không tự động tin mọi tên lớp**. Nên dùng danh sách lớp cho phép và tránh tạo instance hay thực thi method chỉ theo chuỗi từ nguồn không đáng tin.

### 2.1. Những method cơ bản

~~~java
Class<?> type = java.util.ArrayList.class;

System.out.println(type.getName());
System.out.println(type.getSimpleName());
System.out.println(type.getPackageName());
System.out.println(type.isInterface());
System.out.println(type.isRecord());
System.out.println(type.getSuperclass());
~~~

Một số method thường dùng:

| API | Dữ liệu cung cấp |
|---|---|
| **getName()** | Tên nhị phân của lớp, có thể gồm package |
| **getSimpleName()** | Tên ngắn, không bao gồm package |
| **getPackageName()** | Tên package |
| **isInterface()**, **isEnum()**, **isRecord()** | Nhận biết các loại khai báo |
| **getSuperclass()**, **getInterfaces()** | Cấu trúc kế thừa ở mức **Class** |
| **getDeclaredFields()** | Các field được khai báo trực tiếp trong lớp, không gồm field thừa kế |
| **getDeclaredMethods()** | Các method được khai báo trực tiếp, có thể gồm private, synthetic hoặc bridge |
| **getDeclaredConstructors()** | Các constructor được khai báo |
| **getFields()**, **getMethods()** | Các thành phần **public** được nhìn thấy, bao gồm những thành phần kế thừa phù hợp |
| **getRecordComponents()** | Các component của record; **null** nếu kiểu không phải record |
| **getTypeParameters()** | Các biến kiểu generic do lớp/interface khai báo |
| **getGenericSuperclass()** | Kiểu cha với thông tin generic nếu có |
| **getGenericInterfaces()** | Các interface với thông tin generic nếu có |

Các mảng **getDeclaredMethods()** và **getDeclaredFields()** không có cam kết về thứ tự. Nếu công cụ của bạn tạo schema hoặc báo cáo cần thứ tự cố định, hãy chủ động sắp xếp.

**Ngoại lệ quan trọng:** **getRecordComponents()** trả các component theo đúng **thứ tự khai báo trong header record**, vì thứ tự này có ý nghĩa với cấu trúc record.

## 3. Record component không giống Field

Xét một record:

~~~java
record Product(String sku, int quantity) {}
~~~

Record có các component **sku** và **quantity**, đồng thời trình biên dịch tạo ra các thành phần liên quan như field private/final, accessor và canonical constructor.

Chúng có liên hệ, nhưng **không phải một loại metadata duy nhất**:

| Khái niệm | Được biểu diễn bởi | Điều cần biết |
|---|---|---|
| Component trong header record | **RecordComponent** | Tên, kiểu, generic type, annotation, accessor |
| Field lưu component | **Field** | Thành phần dữ liệu ở cấp field, có access control riêng |
| Accessor của component | **Method** | Ví dụ **sku()**, **quantity()** |
| Canonical constructor | **Constructor** | Nhận các tham số tương ứng với component theo thứ tự |

Để dựng metadata từ record, **bắt đầu bằng RecordComponent**, không chỉ liệt kê các field. Dùng **getDeclaredFields()** để suy ra component có thể khiến công cụ nhầm các chi tiết triển khai với hợp đồng record.

### 3.1. isRecord và getRecordComponents

~~~java
import java.lang.reflect.RecordComponent;

record Product(String sku, int quantity) {}

Class<?> recordType = Product.class;

if (recordType.isRecord()) {
    RecordComponent[] components = recordType.getRecordComponents();

    for (RecordComponent component : components) {
        System.out.println(component.getName());
    }
}
~~~

Kết quả:

~~~text
sku
quantity
~~~

Các trường hợp quan trọng:

- Với một **record**, **getRecordComponents()** trả mảng theo thứ tự khai báo; record không có component cho mảng độ dài **0**.
- Với **lớp thường**, **interface**, kiểu nguyên thủy hoặc mảng không phải record, method trả về **null**.
- Vì vậy, hãy kiểm tra **isRecord()** hoặc **components != null** trước khi duyệt.

~~~java
System.out.println(String.class.isRecord());                 // false
System.out.println(String.class.getRecordComponents() == null); // true
~~~

## 4. Các API chính của RecordComponent

Đối tượng **RecordComponent** cung cấp những method đặc thù:

| Method | Mục đích |
|---|---|
| **getName()** | Tên component được khai báo |
| **getType()** | Kiểu theo dạng **Class<?>** sau khi xóa tham số generic |
| **getGenericType()** | Kiểu dưới dạng **Type**, giữ được metadata generic trong khai báo |
| **getAnnotatedType()** | Kiểu kèm annotation đặt tại vị trí sử dụng kiểu |
| **getAccessor()** | Đối tượng **Method** đại diện accessor của component |
| **getDeclaringRecord()** | Đối tượng **Class<?>** của record khai báo component |
| **getAnnotation(AnnotationType.class)** | Đọc một annotation declaration ở component, nếu có tại runtime |
| **getAnnotations()** | Mảng annotation được quan sát trên component |
| **getGenericSignature()** | Chữ ký generic ở mức metadata JVM, không phải API trình bày type chính |

Ví dụ:

~~~java
record Basket(String owner, java.util.List<String> items) {}
~~~

Với component **items**:

~~~java
RecordComponent component =
    Basket.class.getRecordComponents()[1];

System.out.println(component.getName());
System.out.println(component.getType().getTypeName());
System.out.println(component.getGenericType().getTypeName());
~~~

Kết quả:

~~~text
items
java.util.List
java.util.List<java.lang.String>
~~~

**getType()** nhận diện kiểu runtime thô là **List**. **getGenericType()** mô tả đúng khai báo **List<String>** còn được lưu trong metadata biên dịch. Hai câu hỏi này khác nhau và không nên dùng thay nhau.

## 5. Ví dụ đầy đủ: quét record và gọi accessor

Ví dụ sau dùng **Class**, **RecordComponent**, annotation runtime và **Method.invoke**.

Tạo tệp **RecordReflectionDemo.java**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.util.List;

public class RecordReflectionDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface Caption {
        String value();
    }

    public record Product(
        @Caption("Mã sản phẩm") String sku,
        @Caption("Các nhãn") List<String> tags
    ) {}

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<?> type = Product.class;
        Product example = new Product(
            "P-01",
            List.of("java", "reflection")
        );

        System.out.println("Record: " + type.isRecord());

        for (RecordComponent component : type.getRecordComponents()) {
            System.out.println("Name: " + component.getName());
            System.out.println("Raw: "
                + component.getType().getTypeName());
            System.out.println("Generic: "
                + component.getGenericType().getTypeName());

            Caption caption = component.getAnnotation(Caption.class);

            if (caption != null) {
                System.out.println("Caption: " + caption.value());
            }

            Method accessor = component.getAccessor();
            Object componentValue = accessor.invoke(example);

            System.out.println("Value: " + componentValue);
            System.out.println("---");
        }
    }
}
~~~

Chạy với JDK 27:

~~~bash
javac RecordReflectionDemo.java
java RecordReflectionDemo
~~~

Kết quả minh họa:

~~~text
Record: true
Name: sku
Raw: java.lang.String
Generic: java.lang.String
Caption: Mã sản phẩm
Value: P-01
---
Name: tags
Raw: java.util.List
Generic: java.util.List<java.lang.String>
Caption: Các nhãn
Value: [java, reflection]
---
~~~

### Giải thích từng bước

1. **Product.class** cung cấp Class object cho record.
2. **isRecord()** xác nhận cấu trúc là record.
3. **getRecordComponents()** trả hai component theo thứ tự **sku**, **tags**.
4. **getType()** và **getGenericType()** cho biết kiểu thô và kiểu khai báo đầy đủ.
5. **getAnnotation(Caption.class)** đọc nhãn được lưu theo chính sách **RUNTIME**.
6. **getAccessor()** cung cấp method tương ứng với **sku()** hoặc **tags()**.
7. **accessor.invoke(example)** gọi accessor trên record cụ thể và trả kết quả dưới dạng **Object**.

Đoạn code gọi động accessor để **minh họa metadata**. Nếu bạn đã biết đối tượng là **Product**, cách dùng **example.sku()** hoặc **example.tags()** thường đơn giản và phù hợp hơn.

### 5.1. Lỗi khi invoke

**Method.invoke** có thể gặp:

- **IllegalAccessException** nếu caller không được phép gọi method.
- **IllegalArgumentException** nếu target/argument không phù hợp.
- **InvocationTargetException** nếu method được gọi tự ném ngoại lệ; lỗi gốc nằm trong **getCause()**.

Khi một framework gọi method do người dùng cung cấp, đừng xóa cause bằng cách tạo thông điệp lỗi mới rồi bỏ ngoại lệ ban đầu. Nên giữ đầy đủ nguyên nhân để dễ chẩn đoán.

## 6. Annotation của record component

Annotation gắn ngữ nghĩa bổ sung vào khai báo hoặc vị trí sử dụng kiểu. Tuy nhiên, **không phải annotation nào cũng còn tồn tại tại runtime**.

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface DisplayName {
    String value();
}
~~~

Trong đó:

- **@Retention(RetentionPolicy.RUNTIME)** yêu cầu lưu annotation để reflection có thể đọc.
- **@Target(ElementType.RECORD_COMPONENT)** xác định annotation được dùng trên record component.
- **value()** là thành phần của annotation, được đọc qua instance annotation.

Sử dụng:

~~~java
record Employee(
    @DisplayName("Mã nhân viên") String employeeId,
    @DisplayName("Họ tên") String fullName
) {}
~~~

Đọc metadata:

~~~java
for (RecordComponent component :
        Employee.class.getRecordComponents()) {

    DisplayName displayName =
        component.getAnnotation(DisplayName.class);

    if (displayName != null) {
        System.out.println(
            component.getName() + ": " + displayName.value()
        );
    }
}
~~~

### 6.1. Retention có ý nghĩa gì?

| Retention | Khả năng quan sát |
|---|---|
| **SOURCE** | Annotation có trong mã nguồn; không được giữ trong class file |
| **CLASS** | Có thể được lưu trong class file, nhưng không bắt buộc có mặt qua core reflection tại runtime |
| **RUNTIME** | Có thể đọc qua các API annotation reflection tương ứng |

Nếu bạn tạo một annotation cho framework runtime mà quên **@Retention(RUNTIME)**, **getAnnotation(...)** có thể trả về **null** dù annotation nhìn thấy rõ trong mã nguồn.

### 6.2. Annotation declaration khác annotation type-use

Hai ví dụ dưới đây biểu đạt hai vị trí khác nhau:

~~~java
// Annotation gắn vào khai báo component:
@Caption("Nhãn") String name

// Annotation gắn vào cách dùng kiểu:
List<@NonBlank String> tags
~~~

Với trường hợp thứ nhất, tra bằng **RecordComponent.getAnnotation** nếu annotation nhắm đến **RECORD_COMPONENT** và có retention runtime.

Với trường hợp thứ hai, annotation nằm trên **String** là một *type argument* bên trong **List**. Cần đi qua **getAnnotatedType()** và **AnnotatedParameterizedType** để đọc đúng vị trí của nó.

### 6.3. Vị trí annotation có thể được lan truyền

Java có những quy tắc lan truyền annotation từ header record sang các thành phần tương ứng được ngôn ngữ tạo ra, tùy **@Target** và việc khai báo thành phần đó tường minh hay ngầm định.

Vì vậy, không nên cho rằng annotation trên record component tự động xuất hiện ở **mọi** accessor, field hoặc constructor parameter. Hãy xác định mình muốn đọc annotation trên **component**, **field**, **method** hay **parameter**, rồi dùng đúng API và đúng **@Target**.

Với framework thiết kế riêng cho record, đọc trực tiếp **RecordComponent** thường chính xác hơn việc đoán annotation phải nằm ở field hay accessor.

## 7. Type-use annotation và getAnnotatedType()

Ta tạo annotation chỉ dành cho vị trí sử dụng kiểu:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface NonBlank {}
~~~

Khai báo record:

~~~java
record Settings(java.util.List<@NonBlank String> tags) {}
~~~

Annotation **@NonBlank** thuộc **kiểu phần tử String** trong **List<String>**, không phải một annotation declaration trên record component **tags**.

Lấy thông tin:

~~~java
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;

RecordComponent component =
    Settings.class.getRecordComponents()[0];

AnnotatedType annotated = component.getAnnotatedType();

if (annotated instanceof AnnotatedParameterizedType parameterized) {
    AnnotatedType elementType =
        parameterized.getAnnotatedActualTypeArguments()[0];

    boolean isNonBlank =
        elementType.isAnnotationPresent(NonBlank.class);

    System.out.println(isNonBlank); // true
}
~~~

Quy trình:

1. **getAnnotatedType()** lấy kiểu khai báo có thể chứa type-use annotations.
2. **AnnotatedParameterizedType** biểu diễn kiểu dạng **List<...>**.
3. **getAnnotatedActualTypeArguments()** lấy các đối số kiểu đã được chú thích.
4. Tra **NonBlank** trên type argument thích hợp.

Việc annotation tồn tại chỉ là **metadata**. Nó không tự động ngăn tạo **new Settings(List.of(""))**. Phải có code kiểm tra hoặc framework validation thật sự đọc và thực thi quy tắc đó.

## 8. Generic metadata: vì sao cần Type thay vì chỉ Class?

Java generic sử dụng **type erasure**. Sau biên dịch, phần lớn thông tin về type argument của một object không còn được kiểm tra như một kiểu runtime riêng biệt.

Ví dụ:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();

System.out.println(names.getClass() == numbers.getClass()); // true
~~~

Hai đối tượng có cùng lớp runtime là **ArrayList**, không có hai lớp runtime riêng cho **ArrayList<String>** và **ArrayList<Integer>**.

Tuy nhiên, thông tin generic được **khai báo trong chữ ký thành phần hoặc kiểu** có thể được lưu trong class file và được Java reflection tái hiện dưới dạng **Type**.

~~~java
record SearchResult(
    java.util.List<String> names
) {}
~~~

~~~java
RecordComponent component =
    SearchResult.class.getRecordComponents()[0];

System.out.println(component.getType()); // interface java.util.List
System.out.println(component.getGenericType().getTypeName());
// java.util.List<java.lang.String>
~~~

Sự khác biệt cốt lõi:

- **Không thể** từ một **new ArrayList<String>()** thông thường suy ra chắc chắn type argument **String** qua **getClass()**.
- **Có thể** từ khai báo component **List<String> names** lấy được metadata **List<String>** qua **getGenericType()**, nếu metadata được giữ hợp lệ.

Reflection đọc **khai báo**, không khôi phục một cách kỳ diệu mọi tham số generic của mọi object.

## 9. Cây các kiểu Type trong java.lang.reflect

**Type** là interface chung cho một số dạng kiểu được reflection cung cấp.

~~~mermaid
flowchart TD
    T["java.lang.reflect.Type"]
    T --> C["Class<?>"]
    T --> P["ParameterizedType"]
    T --> V["TypeVariable"]
    T --> W["WildcardType"]
    T --> A["GenericArrayType"]
~~~

| Dạng Type | Ví dụ khai báo | Trường hợp sử dụng |
|---|---|---|
| **Class<?>** | **String**, **int**, **String[]**, raw **List** | Kiểu không cần biểu diễn type arguments |
| **ParameterizedType** | **List<String>**, **Map<String, Integer>** | Kiểu có các type arguments |
| **TypeVariable<?>** | **T** trong **class Box<T>** | Tham số kiểu được khai báo |
| **WildcardType** | **?**, **? extends Number**, **? super Integer** | Đại diện wildcard và các bounds |
| **GenericArrayType** | **T[]**, **List<String>[]** trong chữ ký thích hợp | Mảng có kiểu phần tử là type variable hoặc parameterized type |

Cả **Class<?>** và các interface còn lại đều dùng được method **getTypeName()** để tạo chuỗi mô tả kiểu.

### 9.1. Truy cập các type arguments của List

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;

record SearchResult(java.util.List<String> names) {}

Type type =
    SearchResult.class.getRecordComponents()[0].getGenericType();

if (type instanceof ParameterizedType parameterized) {
    Type raw = parameterized.getRawType();
    Type[] arguments = parameterized.getActualTypeArguments();

    System.out.println(raw.getTypeName());
    System.out.println(arguments[0].getTypeName());
}
~~~

Kết quả:

~~~text
java.util.List
java.lang.String
~~~

Với một record component có kiểu **Map<String, List<Integer>>**, **getGenericType()** cũng cho phép duyệt vào các **ParameterizedType** lồng nhau.

**Không nên cast mọi Type sang ParameterizedType.** Với một component **String name**, **getGenericType()** có thể là **String.class**, tức **Class<?>**, không phải ParameterizedType.

### 9.2. TypeVariable của record generic

~~~java
record Box<T extends Number>(
    T value,
    java.util.List<T> history
) {}
~~~

Lấy metadata của type parameter:

~~~java
import java.lang.reflect.TypeVariable;

TypeVariable<?>[] parameters = Box.class.getTypeParameters();

for (TypeVariable<?> parameter : parameters) {
    System.out.println(parameter.getName());

    for (java.lang.reflect.Type bound : parameter.getBounds()) {
        System.out.println(bound.getTypeName());
    }
}
~~~

Kết quả:

~~~text
T
java.lang.Number
~~~

Trong **record Box<T extends Number>**, thành phần **value** có **getGenericType()** là một **TypeVariable** đại diện **T**. Thành phần **history** có **ParameterizedType List<T>**, trong đó type argument cũng là TypeVariable.

Một điểm quan trọng: **Box<Integer>** và **Box<Long>** vẫn dùng cùng **Box.class** ở runtime. Khi chỉ được cung cấp **Box.class**, bạn không biết instance cụ thể đã được gắn tham số kiểu nào trong mã nguồn của người gọi.

### 9.3. WildcardType và giới hạn kiểu

~~~java
record Statistics(
    java.util.List<? extends Number> values
) {}
~~~

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;

Type declared =
    Statistics.class.getRecordComponents()[0].getGenericType();

if (declared instanceof ParameterizedType listType) {
    Type argument = listType.getActualTypeArguments()[0];

    if (argument instanceof WildcardType wildcard) {
        for (Type upper : wildcard.getUpperBounds()) {
            System.out.println(upper.getTypeName());
        }

        for (Type lower : wildcard.getLowerBounds()) {
            System.out.println("lower=" + lower.getTypeName());
        }
    }
}
~~~

Với **? extends Number**, upper bound là **java.lang.Number** và danh sách lower bounds rỗng. Với wildcard không khai báo extends tường minh, upper bound mặc định là **Object**.

Dùng **getUpperBounds()** và **getLowerBounds()** thay vì cố phân tích chuỗi kết quả của **getTypeName()** bằng regular expression.

### 9.4. GenericArrayType

~~~java
record ArrayHolder<T>(T[] values) {}
~~~

~~~java
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.Type;

Type declared =
    ArrayHolder.class.getRecordComponents()[0].getGenericType();

if (declared instanceof GenericArrayType arrayType) {
    System.out.println(
        arrayType.getGenericComponentType().getTypeName()
    );
}
~~~

Kết quả:

~~~text
T
~~~

Nếu component là **String[]**, kiểu khai báo có thể được biểu diễn bằng **Class<?>** của một mảng reifiable. Vì vậy **GenericArrayType** không đại diện cho mọi mảng; nó dành cho mảng mà component type là type variable hoặc parameterized type.

## 10. Generic metadata của class, field và method

Không chỉ record component mới có generic metadata. Java reflection cung cấp API tương ứng trên các khai báo khác.

### 10.1. Field

~~~java
import java.lang.reflect.Field;
import java.util.List;

class RepositoryState {
    List<String> keys;
}

Field field =
    RepositoryState.class.getDeclaredField("keys");

System.out.println(field.getType().getTypeName());
// java.util.List

System.out.println(field.getGenericType().getTypeName());
// java.util.List<java.lang.String>
~~~

**getType()** cung cấp kiểu thô, **getGenericType()** giữ thông tin khai báo generic.

### 10.2. Method

~~~java
import java.lang.reflect.Method;
import java.util.List;

class SearchService {
    public List<String> search(List<Integer> ids) {
        return List.of();
    }
}

Method method =
    SearchService.class.getDeclaredMethod("search", List.class);

System.out.println(method.getReturnType().getTypeName());
// java.util.List

System.out.println(method.getGenericReturnType().getTypeName());
// java.util.List<java.lang.String>

for (java.lang.reflect.Type parameter :
        method.getGenericParameterTypes()) {
    System.out.println(parameter.getTypeName());
}
// java.util.List<java.lang.Integer>
~~~

**getDeclaredMethod** cần danh sách kiểu tham số runtime, chẳng hạn **List.class**, chứ không thể truyền trực tiếp **List<Integer>.class** (cú pháp đó không tồn tại).

### 10.3. Kiểu cha và interface có type arguments

~~~java
class NameList extends java.util.ArrayList<String> {}

java.lang.reflect.Type parent =
    NameList.class.getGenericSuperclass();

System.out.println(parent.getTypeName());
// java.util.ArrayList<java.lang.String>
~~~

Điều này không mâu thuẫn với type erasure. **NameList** đã ghi type argument **String** trong khai báo lớp cha; reflection có thể đọc metadata của chính khai báo này.

Đối với interface, sử dụng **getGenericInterfaces()** và duyệt các **Type** tương ứng.

### 10.4. Metadata của tham số method và constructor

API **Executable.getParameters()** trả các đối tượng **Parameter**. Tuy nhiên, tên tham số thông thường trong class file có thể không được giữ lại, tùy cách biên dịch.

Với mã cần kiểm tra tên tham số của method/constructor, tùy hoàn cảnh có thể cần tùy chọn biên dịch:

~~~bash
javac -parameters Example.java
~~~

Sau đó kiểm tra **Parameter.isNamePresent()** trước khi dựa vào **Parameter.getName()**.

**Riêng tên record component**, dùng **Class.getRecordComponents()** để lấy đúng tên trong header record. Không nên đánh đồng metadata record component với quy tắc giữ tên tham số của method thông thường.

## 11. Constructor của record và truy cập động

Một record có **canonical constructor** với danh sách tham số tương ứng các component theo thứ tự khai báo.

Ví dụ:

~~~java
record Purchase(String id, int quantity) {}
~~~

Có thể lấy constructor theo các kiểu tham số runtime:

~~~java
import java.lang.reflect.Constructor;

Constructor<Purchase> constructor =
    Purchase.class.getDeclaredConstructor(
        String.class,
        int.class
    );

Purchase purchase = constructor.newInstance("P-01", 3);

System.out.println(purchase.id());       // P-01
System.out.println(purchase.quantity()); // 3
~~~

Ví dụ này cần xử lý các ngoại lệ reflection phù hợp, chẳng hạn khai báo **throws ReflectiveOperationException** ở method bao quanh.

**Constructor.newInstance** gọi logic constructor thật của record. Nếu canonical constructor kiểm tra dữ liệu và ném ngoại lệ, reflection không bỏ qua bước kiểm tra đó. Ngoại lệ từ constructor được phản ánh qua **InvocationTargetException**.

Ví dụ xử lý:

~~~java
try {
    constructor.newInstance("P-01", -1);
} catch (java.lang.reflect.InvocationTargetException wrapper) {
    Throwable root = wrapper.getCause();
    System.err.println("Constructor failed: " + root);
}
~~~

Để có ngoại lệ trong ví dụ trên, record phải có logic từ chối **quantity < 0**. Với record **Purchase** trống ở đầu mục, truyền **-1** không tự động gây lỗi: **record không tự sinh validation**.

Khi ứng dụng cần dựng record từ dữ liệu không đáng tin cậy, vừa phải kiểm tra cấu trúc/kiểu, vừa phải áp dụng ràng buộc nghiệp vụ ở constructor hoặc tầng validation.

### 11.1. Không sửa field final của record bằng reflection

Record component tương ứng với field **final** của record. Mô hình record được thiết kế cho dữ liệu ổn định sau khởi tạo; code không nên cố dùng reflection để “mở khóa” và sửa các field đó.

Cách tiếp cận đúng là:

- Gọi canonical constructor để tạo record mới.
- Dùng accessor để đọc giá trị.
- Nếu cần trạng thái mutable thực sự, cân nhắc một class có thiết kế thay đổi trạng thái rõ ràng.

Reflection không phải cơ chế bỏ qua hợp đồng bất biến của record.

## 12. Reflection và module encapsulation trong Java 27

Kể từ khi Java hỗ trợ module, quyền truy cập reflection không chỉ phụ thuộc **public/private** mà còn phụ thuộc module chứa lớp.

Hai khái niệm JPMS cần phân biệt:

- **exports**: cho phép module khác truy cập các **public types/members** của package theo quy tắc ngôn ngữ.
- **opens**: cho phép **deep reflection** vào các thành phần không public của package đối với những module được cho phép, phù hợp với các quy tắc truy cập.

Ví dụ minh họa một **module-info.java**:

~~~java
module sample.model {
    exports sample.model.api;

    opens sample.model.internal to sample.mapper;
}
~~~

Trong ví dụ giả định này:

- Module khác có quan hệ đọc thích hợp có thể dùng public API trong **sample.model.api**.
- Module **sample.mapper** được phép thực hiện deep reflection vào package **sample.model.internal** theo giới hạn của JPMS.
- **opens** không đồng nghĩa với việc các class private hoặc package-private tự trở thành kiểu công khai trong mã nguồn.

Với record public trong package đã export, công cụ có thể dùng accessor public theo cách thông thường mà không cần deep reflection. Nên ưu tiên hợp đồng public thay vì yêu cầu mở toàn bộ package chỉ để truy xuất dữ liệu.

### 12.1. trySetAccessible và giới hạn quyền

Khi một **Method**, **Field** hoặc **Constructor** không thể truy cập theo quy tắc thông thường, **AccessibleObject.trySetAccessible()** cho biết có thể bật quyền truy cập phản chiếu hay không:

~~~java
java.lang.reflect.Method method =
    SomeType.class.getDeclaredMethod("someMethod");

if (method.trySetAccessible()) {
    // Chỉ thực hiện nếu thực sự có quyền và cần deep reflection.
} else {
    // Sử dụng public API hoặc thay đổi thiết kế/module config.
}
~~~

Đoạn trên chỉ là minh họa; **SomeType** và **someMethod** phải được thay bằng kiểu/method thực trong ứng dụng.

Một số điểm quan trọng:

- **trySetAccessible()** trả **false** nếu không thể bật quyền truy cập.
- **setAccessible(true)** có thể ném **InaccessibleObjectException** nếu module không cho phép.
- Truy cập reflection sâu không tự động được phép vào module khác nếu package chưa được mở thích hợp.
- Không nên coi việc mở mọi package hay thêm tham số JVM bypass là giải pháp mặc định cho thiết kế mới.

**Không dùng reflection để vô hiệu hóa phân quyền hoặc đọc dữ liệu nhạy cảm** nằm ngoài phạm vi hợp đồng mà ứng dụng được phép truy cập.

## 13. Thiết kế một bộ mô tả schema record

Một công cụ giản lược có thể dùng metadata để tạo mô tả record mà không truy cập field private.

~~~java
import java.lang.reflect.RecordComponent;
import java.util.ArrayList;
import java.util.List;

record ComponentInfo(
    String name,
    String rawType,
    String genericType
) {}

static List<ComponentInfo> describeRecord(Class<?> type) {
    if (!type.isRecord()) {
        throw new IllegalArgumentException(
            "Chỉ hỗ trợ record: " + type.getName()
        );
    }

    List<ComponentInfo> result = new ArrayList<>();

    for (RecordComponent component : type.getRecordComponents()) {
        result.add(new ComponentInfo(
            component.getName(),
            component.getType().getTypeName(),
            component.getGenericType().getTypeName()
        ));
    }

    return List.copyOf(result);
}
~~~

Sử dụng:

~~~java
record Invoice(String invoiceId, java.util.List<String> lines) {}

for (ComponentInfo component : describeRecord(Invoice.class)) {
    System.out.println(
        component.name() + " => " + component.genericType()
    );
}
~~~

Kết quả:

~~~text
invoiceId => java.lang.String
lines => java.util.List<java.lang.String>
~~~

Ưu điểm của cách thiết kế:

1. Nhận **Class<?>** thay vì chỉ nhận một kiểu record cố định.
2. **isRecord()** xác thực loại khai báo hỗ trợ.
3. Dùng **getRecordComponents()** để giữ đúng danh sách và thứ tự component.
4. Dùng **getGenericType()** để hiển thị phần generic đã được khai báo.
5. Trả một danh sách **ComponentInfo** không thể sửa bằng phương thức thêm/xóa.

Đây mới là **bộ mô tả metadata**, chưa phải serializer hoặc validator hoàn chỉnh. Một schema thực tế còn phải xác định nullability, phạm vi giá trị, versioning, type-use annotations và chính sách xử lý type arguments.

### 13.1. Không biến mọi Type thành Class<?>

Đoạn code sau không an toàn:

~~~java
// Có thể ném ClassCastException:
Class<?> elementType = (Class<?>) component.getGenericType();
~~~

Nếu component là **List<String>**, **getGenericType()** trả **ParameterizedType**, không phải Class.

Giải pháp là xử lý từng dạng **Type**:

~~~java
java.lang.reflect.Type type = component.getGenericType();

if (type instanceof Class<?> raw) {
    System.out.println("Class: " + raw.getName());
} else if (type instanceof java.lang.reflect.ParameterizedType p) {
    System.out.println("Parameterized: " + p.getTypeName());
} else if (type instanceof java.lang.reflect.TypeVariable<?> v) {
    System.out.println("Variable: " + v.getName());
} else if (type instanceof java.lang.reflect.WildcardType w) {
    System.out.println("Wildcard: " + w.getTypeName());
} else if (type instanceof java.lang.reflect.GenericArrayType a) {
    System.out.println("Array: " + a.getTypeName());
}
~~~

Ở đây **component** là một **RecordComponent** đã lấy từ record. Mẫu dùng **instanceof** pattern matching và các API phản chiếu chính thức hiện hành của Java 27.

## 14. Những giới hạn không nên bỏ qua

### 14.1. Type erasure

Reflection đọc được nhiều chữ ký generic **được khai báo**, nhưng không biết chắc type argument của mọi object tại runtime.

~~~java
java.util.List<String> strings = new java.util.ArrayList<>();
Class<?> clazz = strings.getClass();
~~~

**clazz** không chứa “String” trong một instance cụ thể như một đối số kiểu runtime. Nếu một thư viện cần biết **List<String>** để ánh xạ dữ liệu, hãy cung cấp **Type** từ một khai báo thích hợp hoặc một đối tượng đại diện kiểu được tạo theo hợp đồng thư viện.

### 14.2. Metadata có thể không đủ hoặc không nhất quán

Reflection đọc class file đã được tải. Dữ liệu generic có thể gây lỗi như:

- **GenericSignatureFormatError** nếu generic signature trong class file không hợp lệ.
- **TypeNotPresentException** nếu chữ ký generic tham chiếu tới một kiểu không hiện diện.
- **MalformedParameterizedTypeException** nếu một parameterized type không hợp lệ.

Các lỗi này hiếm gặp trong project Java được biên dịch nhất quán nhưng đáng quan tâm khi framework đọc class file từ plugin hoặc thư viện độc lập.

### 14.3. Thứ tự duyệt metadata

**RecordComponent[]** có thứ tự khai báo được bảo đảm; các mảng thông thường từ **getDeclaredMethods()**, **getDeclaredFields()** không có thứ tự ổn định được bảo đảm.

Nếu tạo JSON schema, tài liệu API hoặc cache key từ metadata, hãy dùng thứ tự record component hoặc áp dụng tiêu chí sort tường minh.

### 14.4. Hiệu năng và caching

Reflection làm việc với metadata ở runtime và việc gọi động có chi phí/đặc tính tối ưu khác lời gọi trực tiếp. Trong framework:

- Khám phá metadata một lần khi khởi tạo adapter.
- Cache **Method**, **Constructor**, **RecordComponent** hoặc mô tả đã chuẩn hóa khi hợp lý.
- Lưu ý **ClassLoader** và vòng đời cache khi ứng dụng hỗ trợ plugin tải/gỡ động.
- Chỉ tối ưu sau khi đo, thay vì giả định mọi lời gọi reflection đều là nút thắt.

### 14.5. Ranh giới tin cậy

Không sử dụng tên lớp, tên method hoặc tên field từ người dùng để tự động gọi **Class.forName**, **Method.invoke** hoặc mở truy cập vào thành phần private mà không có allowlist và kiểm soát quyền.

Metadata phản chiếu có thể làm lộ tên nội bộ, annotation hoặc cấu trúc ứng dụng. Chỉ công bố những thông tin nằm trong hợp đồng API được phép.

## 15. So sánh các API thường bị nhầm

| Cặp API | Khác biệt cần nhớ |
|---|---|
| **getRecordComponents()** và **getDeclaredFields()** | Component là hợp đồng record; Field là thành phần lưu trữ cấp lớp |
| **getType()** và **getGenericType()** | Class sau type erasure so với Type mô tả generic khai báo |
| **getGenericType()** và **getAnnotatedType()** | Loại generic so với cách dùng kiểu kèm annotation |
| **getAnnotation()** của component và **getAnnotation()** của accessor | Hai vị trí metadata riêng; phụ thuộc target/propagation |
| **getMethods()** và **getDeclaredMethods()** | Public/inherited so với những method khai báo trực tiếp, mọi mức truy cập |
| **getSuperclass()** và **getGenericSuperclass()** | Class cha thô so với Type có thể chứa type arguments |
| **Parameter.getName()** và **RecordComponent.getName()** | Tên tham số method phụ thuộc metadata biên dịch; tên record component có trong Record metadata |
| **exports** và **opens** | Public API cấp module so với quyền deep reflection |
| **Method.invoke()** và gọi method trực tiếp | Dynamic invocation so với lời gọi kiểm tra tại compile time |
| **Class.forName()** và **SomeType.class** | Tải/tra lớp bằng tên động so với kiểu đã biết khi biên dịch |

## 16. Các lỗi thường gặp và hướng khắc phục

| Lỗi hoặc hiểu nhầm | Tình huống | Cách xử lý |
|---|---|---|
| **NullPointerException** khi duyệt record components | Gọi **getRecordComponents()** trên lớp không phải record | Kiểm tra **isRecord()** trước |
| **ClassCastException** khi cast Type sang Class | Component có kiểu **List<String>** | Xử lý **ParameterizedType** |
| Cho rằng **getClass()** lưu đối số generic của object | Một **ArrayList<String>** được tạo trực tiếp | Phân biệt generic signature khai báo và type erasure |
| Không đọc thấy annotation trong runtime | Annotation mặc định có retention không phải RUNTIME | Khai báo **@Retention(RUNTIME)** |
| Đọc type-use annotation bằng **component.getAnnotation()** | Annotation nằm trên phần tử kiểu **List<@A String>** | Dùng **getAnnotatedType()** và **AnnotatedParameterizedType** |
| Dựa vào thứ tự **getDeclaredFields()** | Thứ tự không được bảo đảm | Với record dùng **getRecordComponents()** |
| Dùng **getDeclaredMethod("f", List<String>.class)** | Không có class literal cho parameterized type | Dùng **List.class** để tra method, rồi đọc generic metadata |
| **IllegalAccessException** khi invoke | Thành phần không được phép truy cập | Ưu tiên public API; kiểm tra module |
| **InaccessibleObjectException** khi setAccessible | Package không mở cho deep reflection | Chỉnh thiết kế hoặc **opens** có phạm vi phù hợp |
| Bỏ cause của **InvocationTargetException** | Method/constructor bên trong ném lỗi | Đọc **getCause()** và giữ nguyên ngữ cảnh |
| Cố sửa field final của record | Muốn cập nhật một component | Tạo record mới qua constructor |
| Cho rằng annotation tự thực thi validation | Metadata chưa được một framework đọc | Xây dựng validator hoặc dùng framework thích hợp |
| Lấy tên tham số tùy ý sau biên dịch | Class không có metadata tên tham số | Dùng **-parameters** khi cần; record component có API riêng |
| Dùng reflection ở mọi lớp dịch vụ | Tăng độ phức tạp và mất kiểm tra tĩnh | Dùng reflection tại ranh giới framework thật sự cần |
| Cho tên lớp không tin cậy vào **Class.forName** | Plugin/config bị điều khiển ngoài hệ thống | Dùng danh sách lớp cho phép, xác thực cấu hình |

## 17. Bài thực hành

Hãy xây dựng một công cụ tạo schema cho các record:

~~~java
record User(
    String userId,
    java.util.List<String> roles,
    java.util.Map<String, Integer> scores
) {}
~~~

Yêu cầu:

1. Hàm **describe(Class<?> type)** chỉ chấp nhận record; nếu không phải record thì báo lỗi rõ ràng.
2. Với mỗi component, xuất **name**, **raw type**, **generic type**, theo đúng thứ tự khai báo.
3. Với component **roles**, lấy **String** từ **List<String>** bằng **ParameterizedType**.
4. Với component **scores**, lấy hai type arguments **String** và **Integer** từ **Map<String, Integer>**.
5. Tạo annotation declaration **@Label** có **@Target(RECORD_COMPONENT)** và **@Retention(RUNTIME)** để hiển thị tên tiếng Việt.
6. Thêm type-use annotation vào một phần tử generic, rồi đọc bằng **AnnotatedParameterizedType**.
7. Viết kiểm thử cho một lớp thường để bảo đảm code không duyệt một mảng **null**.
8. Kiểm tra framework không cần deep reflection vào private fields khi chỉ muốn đọc record components và gọi accessor public.

Bài thực hành này giúp bạn xây dựng đúng tư duy: **metadata được mô tả có kiểu**, không phải chỉ là chuỗi có thể ghép tùy ý.

## 18. Ghi nhớ

- **Reflection** cho phép khám phá kiểu và thành phần Java tại runtime; chỉ nên dùng khi thực sự cần dynamic metadata hoặc invocation.
- **Class<?>** là điểm vào để kiểm tra kiểu và đọc method, field, constructor, generic và record metadata.
- **Class.isRecord()** kiểm tra một lớp có phải record hay không.
- **Class.getRecordComponents()** trả các **RecordComponent** theo thứ tự khai báo, hoặc **null** với kiểu không phải record.
- **RecordComponent.getName/getType/getGenericType/getAccessor** là các API cốt lõi để mô tả record.
- **getType()** trả dạng **Class<?>**; **getGenericType()** trả **Type** có thể giữ type arguments từ khai báo.
- **Type** có các dạng **Class**, **ParameterizedType**, **TypeVariable**, **WildcardType**, **GenericArrayType**; đừng cast tất cả về Class.
- **Type erasure** khiến runtime object không tự mang đầy đủ đối số generic, nhưng signature của class/method/component vẫn có thể giữ generic metadata.
- Annotation muốn đọc tại runtime phải có retention phù hợp; **RECORD_COMPONENT** và **TYPE_USE** là hai vị trí khác nhau.
- **getAnnotatedType()** dùng để tìm type-use annotations, kể cả bên trong parameterized types.
- Reflection phải tuân theo module access; **exports** không đồng nghĩa **opens**, và **setAccessible(true)** không bỏ qua mọi ranh giới module.
- Tránh chỉnh sửa record field bằng reflection; đọc qua accessor và tạo record mới bằng constructor.
- Kiểm tra lỗi invocation qua **InvocationTargetException.getCause()**, cache metadata có chủ đích và không cho dữ liệu không tin cậy tự quyết định lớp/method được gọi.

## Tài liệu tham khảo

- [Java SE 27 API — Class](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Class.html)
- [Java SE 27 API — RecordComponent](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Java SE 27 API — java.lang.reflect](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/package-summary.html)
- [Java SE 27 API — Type](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Type.html)
- [Java SE 27 API — ParameterizedType](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/ParameterizedType.html)
- [Java SE 27 API — TypeVariable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/TypeVariable.html)
- [Java SE 27 API — WildcardType](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/WildcardType.html)
- [Java SE 27 API — GenericArrayType](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/GenericArrayType.html)
- [Java SE 27 API — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [Java SE 27 API — AccessibleObject](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java SE 27 API — Method](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html)
- [Java Language Specification, Java SE 27 — §8.10 Record Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Language Specification, Java SE 27 — §9.6.4.1 Annotation Target](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.6.4.1)
