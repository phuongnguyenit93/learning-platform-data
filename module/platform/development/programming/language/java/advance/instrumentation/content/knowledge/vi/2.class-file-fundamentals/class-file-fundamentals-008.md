# Annotation, synthetic, bridge, lambda và mã do trình biên dịch sinh trong Java class file

> **Mục tiêu:** Khi nhìn một file `.class`, phân biệt cấu trúc thực sự do lập trình viên khai báo với metadata và mã do trình biên dịch/runtime tạo ra; hiểu vai trò của annotation, cờ `ACC_SYNTHETIC`, `ACC_BRIDGE`, generic bridge method và lambda dùng `invokedynamic`; từ đó chọn đúng điểm instrumentation, tránh bỏ sót hoặc ghi nhận trùng sự kiện.

## 1. Vì sao code trong `.class` không giống hoàn toàn code Java đã viết?

Java source không được JVM chạy trực tiếp. `javac` chuyển source thành những định nghĩa lớp, field, method, bytecode và **attributes** trong file `.class`. Trong quá trình này, compiler phải thực hiện những nghĩa vụ của ngôn ngữ mà source không nêu bằng một phương thức cụ thể: bảo toàn đa hình sau generic erasure, triển khai lambda, lưu annotation có retention thích hợp, tạo constructor hoặc phương thức hỗ trợ khi cần.

Ví dụ source chỉ có một phương thức `String convert(String)`, nhưng class file có thể còn một phương thức `Object convert(Object)` để duy trì tương thích với kiểu generic đã bị xóa. Một lambda `x -> x.trim()` có thể tương ứng với lệnh `invokedynamic`, một phương thức triển khai mang tên do compiler chọn và một đối tượng functional interface được tạo lúc chạy. Một annotation `@Tag` có thể chỉ còn là metadata, hoàn toàn không xuất hiện như lệnh được thực thi.

Đây là vấn đề thực tế của **instrumentation**:

- Nếu agent đếm mọi method entry, một lời gọi nghiệp vụ có thể bị đếm hai lần vì đi qua cả **bridge method** và method gốc.
- Nếu lọc mọi method `synthetic`, agent có thể bỏ sót code **thực sự chạy** trong phần thân lambda.
- Nếu chỉ dùng Java Reflection để tìm annotation, agent sẽ không thấy những annotation có retention `CLASS`.
- Nếu tìm một file `SomeClass$$Lambda...class` trên đĩa, có thể không thấy vì implementation của lambda được tạo lúc chạy và có thể là **hidden class**.
- Nếu tin rằng mọi `invokedynamic` đều là lambda, agent dễ hiểu nhầm các call site dùng cho mục đích khác, chẳng hạn nối chuỗi.

**Nguyên tắc:** Mỗi cấu trúc ở class file có một vai trò khác nhau: metadata mô tả, method bytecode thực thi, cờ access mô tả tính chất method, và bootstrap/call site tham gia liên kết hành vi. Phải biết đang đọc loại nào trước khi quyết định chèn probe.

## 2. Bản đồ các thành phần cần nhận diện

| Thành phần | Biểu hiện điển hình ở class file | Ý nghĩa chính | Ảnh hưởng tới instrumentation |
| --- | --- | --- | --- |
| **Annotation** | `RuntimeVisibleAnnotations`, `RuntimeInvisibleAnnotations`, thuộc tính annotation theo parameter/type | Metadata trên khai báo hoặc vị trí dùng kiểu | Chọn thành phần cần theo dõi; không mặc nhiên là code chạy |
| **Synthetic** | Cờ `ACC_SYNTHETIC` hoặc thuộc tính `Synthetic` ở class/member tương ứng | Thành phần không xuất hiện trực tiếp như khai báo trong source | Tránh coi tất cả là API người dùng; vẫn có thể chứa bytecode quan trọng |
| **Bridge method** | Cờ method `ACC_BRIDGE`, thường kèm `ACC_SYNTHETIC` với `javac` | Duy trì polymorphism khi descriptor bị thay đổi do generic erasure hoặc covariant return | Có thể tạo thêm một tầng gọi dẫn tới thống kê trùng |
| **Lambda / method reference** | `invokedynamic`, mục `BootstrapMethods`, method handle, có thể có method `lambda$...` | Tạo hành vi functional interface thông qua liên kết động | Không thể chỉ quét các method khai báo theo tên Java source |
| **Các thành phần compiler sinh khác** | Constructor, accessor, field phụ trợ, lệnh trong method, thuộc tính đặc biệt | Thực hiện các quy tắc ngôn ngữ Java | Không phải mọi mã được sinh đều có tên riêng hay cờ `synthetic` |

Những biểu hiện trên phụ thuộc compiler, target bytecode và phiên bản JDK. **Hành vi được đặc tả** cần tách khỏi **cách `javac` hiện thực**.

## 3. Annotation: metadata được giữ ở đâu và sống bao lâu?

Annotation là metadata gắn vào một khai báo hoặc, khi phù hợp với `@Target`, vào vị trí dùng một kiểu. Nó có thể được compiler, annotation processor, framework, công cụ phân tích class file hoặc Reflection đọc. Việc có annotation **không khiến JVM tự động chạy một interceptor**. Một framework chỉ thay đổi hành vi khi nó thực sự tìm và xử lý annotation đó.

### 3.1. `@Retention`: SOURCE, CLASS và RUNTIME

| Retention | Có trong `.class` theo biên dịch Java chuẩn? | Đọc qua Java Reflection lúc chạy? | Ví dụ mục đích |
| --- | --- | --- | --- |
| `SOURCE` | Không; bị loại khi biên dịch | Không | Hướng dẫn compiler/IDE, kiểm tra ở source |
| `CLASS` | Có | Không qua Reflection thông thường | Phân tích bytecode, công cụ build; đây là **giá trị mặc định** nếu không khai báo `@Retention` |
| `RUNTIME` | Có | Có, nếu đọc đúng phần tử và API | Framework hoặc công cụ runtime tìm metadata |

Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeTag {}

@Retention(RetentionPolicy.CLASS)
@interface ClassTag {}

@Retention(RetentionPolicy.SOURCE)
@interface SourceTag {}
```

Khi một lớp dùng các annotation này, class file có thể chứa hai annotation đầu; annotation `SOURCE` không được giữ lại trong artifact đích. `ClassTag` không xuất hiện ở `Class.isAnnotationPresent(...)` theo API Reflection thông thường, dù bytecode parser có thể nhìn thấy thuộc tính của nó.

Trong class file, tên `RuntimeVisibleAnnotations` và `RuntimeInvisibleAnnotations` mô tả **mức hiển thị qua Reflection**, không có nghĩa annotation “vô hình” là vô dụng. Công cụ đọc bytecode như ASM có thể quan sát cả hai tập. Các thuộc tính tương ứng cũng tồn tại cho annotation trên parameter hoặc type-use, chẳng hạn `RuntimeVisibleParameterAnnotations` và `RuntimeVisibleTypeAnnotations`.

### 3.2. `@Target` quyết định nơi đặt, không quyết định retention

`@Target(ElementType.METHOD)` cho phép annotation trên khai báo method. `@Target(ElementType.TYPE_USE)` cho phép annotation ở vị trí dùng kiểu, chẳng hạn:

```java
// Ví dụ cấu trúc (không phải file chạy độc lập):
@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface NonNull {}

List<@NonNull String> names;
```

Annotation trên `String` ở đây là **type-use annotation**, không đồng nhất với annotation trên declaration của field `names`. Một scanner chỉ tìm `RuntimeVisibleAnnotations` trên field có thể bỏ lỡ `RuntimeVisibleTypeAnnotations`. Tương tự, annotation trên tham số cần đọc đúng bảng parameter, và tên tham số không tự động có sẵn nếu compiler không phát sinh metadata phù hợp.

Các annotation như `@Override`, `@SuppressWarnings` thường hữu ích ở bước biên dịch, không phải cơ chế đặt probe runtime. Trái lại một annotation tự định nghĩa có `RUNTIME` có thể được framework quét khi khởi tạo.

### 3.3. Annotation processor khác với runtime instrumentation

Một **annotation processor** hoạt động ở thời gian biên dịch, đọc mô hình source/element và có thể sinh thêm file source/resource. Nó không giống Java agent can thiệp vào bytecode khi JVM nạp lớp.

Ví dụ phân biệt:

```text
Source + annotation
      ├─ compiler/annotation processor → file được tạo ở build time
      └─ compiler → .class + annotation metadata còn được giữ
                                              ↓
                                JVM / Reflection / Java agent
```

Annotation chỉ là tín hiệu dữ liệu. Không phải mọi annotation `RUNTIME` đều được framework quét và không phải annotation `CLASS` là vô nghĩa với agent. Để quyết định instrument theo annotation, hãy xác định rõ công cụ đọc source, bytecode hay Reflection.

### 3.4. Cẩn thận khi di chuyển hoặc sửa annotation

Một bytecode transformer phải bảo toàn annotation liên quan nếu không có chủ đích sửa chúng. Điều đó bao gồm thuộc tính ở class, method, field, parameter và type-use. Riêng `AnnotationDefault` lưu giá trị mặc định trên method của annotation type; `Signature`, `MethodParameters` hoặc debug attributes là metadata khác, **không phải annotation**.

Nếu agent tạo phương thức wrapper và copy annotation một cách thiếu suy nghĩ, kết quả có thể khiến framework thấy annotation ở nhiều method hoặc trên method khác với dự định. Ngay cả việc lấy annotation theo `getDeclaredAnnotations()` và `getAnnotations()` cũng có khác biệt do kế thừa annotation cấp class; `@Inherited` không có nghĩa mọi method annotation tự kế thừa sang override.

## 4. Synthetic: thành phần compiler tạo, nhưng không đồng nghĩa “bỏ qua”

`ACC_SYNTHETIC` là một access flag mô tả thành phần **không xuất hiện trực tiếp như khai báo trong source**. Trong định dạng class file còn có thuộc tính `Synthetic` phục vụ tương thích với những trường hợp/phiên bản liên quan. Với Java Reflection:

- `Class.isSynthetic()` cho biết tính synthetic của lớp.
- `Method.isSynthetic()` cho biết tính synthetic của method.
- `Field.isSynthetic()` cho biết tính synthetic của field.
- `Method.isBridge()` hỏi **một điều khác**: method có cờ bridge hay không.

Ví dụ một compiler có thể sinh method riêng để chứa phần thân lambda; method đó thường mang `ACC_SYNTHETIC`. Nhưng method đó có thể thực thi business logic thực sự. Nếu agent loại trừ vô điều kiện mọi synthetic method, nó có thể bỏ mất đoạn xử lý được viết bằng lambda.

Ngược lại, có các thành phần xuất hiện trong `.class` dù source không có khai báo tương ứng mà **không được đảm bảo** có cờ `synthetic`: constructor mặc định, method do record/enum yêu cầu, lệnh để thực hiện `try-with-resources`, những chuyển đổi bên trong method, v.v. Không thể dùng `isSynthetic()` làm bộ phân loại đầy đủ của “mã compiler sinh”.

### 4.1. Dấu hiệu nào đáng tin?

Một số kiểu tên thường được thấy trong output của `javac`: `lambda$...`, `$VALUES`, `$SwitchMap...`, `access$...`. **Đừng dựa vào những tên này làm giao ước ổn định.** Chúng là chi tiết triển khai, có thể khác giữa JDK/phiên bản compiler/cấu trúc source, và một số không còn xuất hiện trong các phiên bản mới. Chẳng hạn JVM hỗ trợ cơ chế *nestmates* từ Java 11, giúp nhiều truy cập giữa các lớp trong cùng nest không còn cần synthetic accessor theo cách compiler cũ từng dùng.

Đối với agent, cần kết hợp access flags, method descriptor, owner/class loader, annotation, instruction và vị trí gọi. Một `synthetic` method có thể là “chi tiết nội bộ cần tránh công bố như API”, nhưng vẫn là một điểm đo hữu ích khi muốn hiểu đường chạy.

### 4.2. Thứ nào là “không do source khai báo”?

- **Synthetic member:** có đánh dấu phù hợp theo class-file flags/metadata; API Reflection có thể kiểm tra.
- **Compiler-generated instruction:** bytecode được compiler thêm vào một method, **không nhất thiết tồn tại dưới dạng member mới**.
- **Generated source:** một annotation processor hoặc generator xuất ra `.java`; khi `javac` biên dịch, member từ source sinh đó **không tự động có `ACC_SYNTHETIC`**.
- **Generated runtime class:** một proxy/lambda implementation được tạo khi chương trình chạy; cần xem cơ chế định nghĩa lớp và thông tin runtime riêng.

Bốn trường hợp trên dễ bị gọi chung là “code sinh”, nhưng cách tìm và instrument khác nhau.

## 5. Bridge method: vì sao một lời gọi có thể chạy qua hai method?

### 5.1. Generic erasure làm thay đổi descriptor

Xét hai lớp:

```java
class Parent<T> {
    public T convert(T value) {
        return value;
    }
}

class Child extends Parent<String> {
    @Override
    public String convert(String value) {
        return value.trim();
    }
}
```

Trong Java source, `Child.convert(String)` ghi đè `Parent<String>.convert(String)`. Nhưng generic **bị xóa tại bytecode**: method của `Parent<T>` có descriptor tương đương `(Ljava/lang/Object;)Ljava/lang/Object;`. Trong khi method thực do `Child` khai báo có descriptor `(Ljava/lang/String;)Ljava/lang/String;`.

Để lời gọi đa hình qua một tham chiếu `Parent<String>` vẫn tới `Child`, `javac` thường sinh một **bridge method** trong `Child`:

```java
// GIẢ MÃ để diễn tả bridge, không phải Java source được phép khai báo
// cùng lúc với convert(String) theo cách này:
public Object convert(Object value) {
    return convert((String) value);
}
```

Trong file class, method bridge có cờ `ACC_BRIDGE`, thường có thêm `ACC_SYNTHETIC`. Nó thực hiện ép kiểu rồi chuyển tới method đặc thù. Do đó:

```text
Parent<String> p = new Child();
p.convert("  hi  ");
       │
       ▼
Child.convert(Object)     [bridge, descriptor sau erasure]
       │ cast sang String
       ▼
Child.convert(String)     [logic do lập trình viên viết]
```

Hai lần vào method không có nghĩa có hai thao tác nghiệp vụ. Nếu instrument cả hai entry và ghi `business.operation.count++`, cùng một lời gọi có thể bị đếm hai lần. Nếu đo duration của cả hai và cộng chúng như những công việc độc lập, có thể tính trùng khoảng thời gian lồng nhau.

### 5.2. Bridge còn có thể xuất hiện ngoài ví dụ generic

Ngoài generic erasure, **covariant return type** cũng có thể đòi hỏi bridge để giữ tính đa hình ở mức descriptor của JVM. Ví dụ một lớp con trả `String` trong khi lớp cha có method trả `Object`. Đặc tả Java định nghĩa semantics của overriding; compiler có trách nhiệm tạo bytecode bảo toàn chúng.

Không phải bridge đều thuộc cùng một quy tắc tên; cần kiểm tra `ACC_BRIDGE`, chữ ký bytecode và call path thực. Cũng đừng nhầm `ACC_BRIDGE` của method trong class file với hằng `LambdaMetafactory.FLAG_BRIDGES` dùng trong một trường hợp liên kết lambda: chúng nằm ở **hai giao diện/cấp độ khác nhau**.

### 5.3. Khi có raw type hoặc Reflection

Vì bridge nhận `Object`, lời gọi qua raw `Parent` có thể đi tới bridge rồi gây `ClassCastException` nếu truyền kiểu không hợp lệ. Điều đó là một phần bảo vệ kiểu ở runtime, không phải lỗi do instrumentation tự tạo. Java Reflection với `getDeclaredMethods()` cũng có thể trả cả method bridge và method thực; khi tự động duyệt Reflection, phải lọc hoặc gộp để không lặp cùng một logical operation.

## 6. Lambda: `invokedynamic`, bootstrap và phần thân được thực thi

Lambda là biểu thức Java tạo đối tượng thực thi một **functional interface**. Source:

```java
Function<String, String> formatter = s -> s.trim().toUpperCase();
String result = formatter.apply("  java  ");
```

Với `javac` hiện đại, bytecode ở nơi đánh giá biểu thức lambda thường chứa **`invokedynamic`**, kết hợp bootstrap method do `LambdaMetafactory` cung cấp. Đặc tả API mô tả ba giai đoạn có ý nghĩa:

1. **Linkage:** Lần đầu liên kết call site, bootstrap `LambdaMetafactory` xây dựng `CallSite` phù hợp; phương án tạo/tái sử dụng class là chi tiết runtime.
2. **Capture:** Khi đánh giá biểu thức lambda, target của call site tạo hoặc lấy một đối tượng functional interface, có thể giữ các giá trị được capture (nếu có). Không được dựa vào identity của các object này như giao ước.
3. **Invocation:** Khi gọi `formatter.apply(...)`, implementation được mô tả bằng `MethodHandle` thực thi cùng tham số nhận và các captured values.

Sơ đồ khái niệm:

```text
Source: s -> s.trim().toUpperCase()
          │ javac
          ▼
caller bytecode: invokedynamic   → bootstrap: LambdaMetafactory
          │                                     │
          │                           liên kết CallSite
          ▼                                     │
  Function instance  ◀──────────────────────────┘
          │
       apply("  java  ")
          │
          ▼
  implementation method/handle
          │
          ▼
       "JAVA"
```

`javac` thường đặt phần thân lambda vào một method có tên dạng `lambda$...` trong lớp chứa biểu thức; method này thường synthetic. Nhưng **method reference** như `String::trim` có thể liên kết trực tiếp tới method đã có và không cần tạo `lambda$...` tương ứng. Một lambda cũng có thể capture biến cục bộ `effectively final` hay `this`; số tham số trong method handle có thể khác bề ngoài functional-interface method vì có captured arguments.

### 6.1. Đối tượng lambda có class ở đâu?

Lambda implementation có thể được tạo động và không có file `.class` riêng trong JAR. Những JDK hiện đại có thể dùng **hidden classes** cho implementation. Đừng suy ra có thể lấy toàn bộ lambda implementation bằng cách quét class path hoặc dựa vào tên class kiểu `$$Lambda`. Một số runtime API/agent cơ bản có giới hạn đối với hidden class, retransformation hoặc cách nhìn thấy class do runtime sinh.

Đồng thời, `invokedynamic` **không dành riêng** cho lambda. Trong Java hiện đại, nối chuỗi bằng `+` thường cũng dùng call site có bootstrap thuộc `StringConcatFactory`. Muốn xác định call site dành cho lambda, hãy xem `BootstrapMethods`, bootstrap method handle và cách nó liên kết tới functional interface, thay vì chỉ tìm opcode `invokedynamic`.

### 6.2. Instrumentation nên đặt probe ở đâu?

Có ba loại vị trí khác nhau:

| Vị trí | Thu được gì? | Điểm cần thận trọng |
| --- | --- | --- |
| Nơi **tạo** lambda (call site `invokedynamic`) | Khi biểu thức được đánh giá / object được capture | Không đồng nghĩa body đã chạy; lambda có thể được tạo mà chưa gọi |
| Method implementation hoặc `lambda$...` | Thời điểm phần thân chạy | Có thể compiler-dependent; phải xử lý synthetic, method handle, class loader |
| Ranh giới functional interface method (ví dụ `Function.apply`) | Lúc đối tượng được gọi | Chỉ chọn đúng implementation; tránh instrument mọi `apply` một cách quá rộng hoặc lặp điểm đo |

Với lambda bất đồng bộ, thời điểm tạo lambda, thời điểm submit task và thời điểm task thực sự chạy còn có thể cách xa nhau; một span có thể cần context propagation và quy tắc kết thúc phù hợp. Nếu chỉ đo lambda expression creation thì không phản ánh thời gian chạy callback.

## 7. Thí nghiệm Java 17+: xem annotation, bridge, synthetic và lambda

Tạo **một file duy nhất** có tên `ClassFileArtifactsDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.function.Function;

public class ClassFileArtifactsDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface RuntimeTag {}

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.TYPE)
    @interface ClassTag {}

    @Retention(RetentionPolicy.SOURCE)
    @Target(ElementType.TYPE)
    @interface SourceTag {}

    static class Parent<T> {
        public T convert(T input) {
            return input;
        }
    }

    @RuntimeTag
    @ClassTag
    @SourceTag
    static final class Child extends Parent<String> {
        @Override
        public String convert(String input) {
            return input.trim();
        }
    }

    public static void main(String[] args) {
        Parent<String> throughParent = new Child();
        System.out.println("bridge call: " + throughParent.convert("  hi  "));

        Method[] methods = Child.class.getDeclaredMethods();
        long bridgeCount = Arrays.stream(methods)
                .filter(Method::isBridge)
                .count();
        long syntheticBridgeCount = Arrays.stream(methods)
                .filter(m -> m.isBridge() && m.isSynthetic())
                .count();
        System.out.println("bridge methods: " + bridgeCount);
        System.out.println("bridge synthetic: " + syntheticBridgeCount);

        System.out.println("runtime annotation: "
                + Child.class.isAnnotationPresent(RuntimeTag.class));
        System.out.println("class annotation at runtime: "
                + Child.class.isAnnotationPresent(ClassTag.class));
        System.out.println("source annotation at runtime: "
                + Child.class.isAnnotationPresent(SourceTag.class));

        String prefix = "value=";
        Function<String, String> formatter =
                value -> prefix + throughParent.convert(value);
        System.out.println("lambda: " + formatter.apply(" ok "));
    }
}
```

Chạy bằng JDK 17 trở lên, dùng `javac` của JDK (không phải một trình biên dịch thay thế):

```bash
javac -encoding UTF-8 ClassFileArtifactsDemo.java
java ClassFileArtifactsDemo
```

**Stdout dự kiến với `javac` JDK 17+:**

```text
bridge call: hi
bridge methods: 1
bridge synthetic: 1
runtime annotation: true
class annotation at runtime: false
source annotation at runtime: false
lambda: value=ok
```

Giải thích kết quả:

- `throughParent.convert(...)` dùng kiểu static `Parent<String>` nhưng dispatch tới `Child`. `javac` cung cấp bridge `convert(Object)` để giữ đường dispatch này.
- Reflection thấy một bridge method của `Child`, và `javac` đánh dấu nó synthetic.
- `RuntimeTag` được Reflection nhìn thấy; `ClassTag` vẫn tồn tại trong class file nhưng không trả qua Reflection thông thường; `SourceTag` bị bỏ khi biên dịch.
- Lambda capture cả `prefix` và `throughParent`. Khi gọi `apply`, body thực thi `convert`, tạo `"value=ok"`. Dòng output không tiết lộ implementation lambda được sinh dưới hình thức class nào.

### 7.1. Đọc class file bằng `javap`

Dùng những lệnh sau (tên có `$` được đặt trong dấu nháy đơn cho Bash/PowerShell):

```bash
javap -c -p ClassFileArtifactsDemo
javap -v -p ClassFileArtifactsDemo
javap -v -p 'ClassFileArtifactsDemo$Child'
```

Trong Windows `cmd.exe`, dùng dấu nháy kép ở tên lớp chứa `$` thay cho dấu nháy đơn. `javap -p` cho phép hiển thị member private; `-c` in instruction; `-v` in thêm flags, descriptors, attributes và bootstrap entries.

Những điều **cần tìm**, không phụ thuộc số thứ tự constant pool cụ thể:

1. Ở `Child`, có hai descriptor liên quan tới `convert`: một nhận/trả `String`, một nhận/trả `Object`. Cái sau có `ACC_BRIDGE`, `ACC_SYNTHETIC`; body chuyển tới method kiểu `String`.
2. Ở metadata của `Child`, `RuntimeTag` thuộc nhóm `RuntimeVisibleAnnotations` và `ClassTag` thuộc `RuntimeInvisibleAnnotations`. Không có annotation instance của `SourceTag`.
3. Ở class chính, tìm `invokedynamic` liên quan tới `Function`. Trong `BootstrapMethods`, tìm mục tham chiếu `java/lang/invoke/LambdaMetafactory` và method handle trỏ tới body được triển khai.
4. Với `javac` của JDK 17+, có thể thấy method private synthetic mang tên dạng `lambda$main$0` trong class chính. Cấu trúc/naming không phải API để công cụ phụ thuộc lâu dài.
5. Có thể xuất hiện `invokedynamic` khác do nối chuỗi; bootstrap `StringConcatFactory` **không phải** lambda.

Mục tiêu của `javap` là **xác nhận artifact**, không suy diễn từ bản source hoặc từ tên method. Nếu compiler/JDK khác tạo hình dạng khác, hãy kiểm tra output thực rồi giải thích theo descriptor, flags và bootstrap owner.

### 7.2. Hai phép kiểm khác nhau

**Kiểm bằng Reflection** trả lời: *Tại runtime, public API thấy metadata/member nào?*

```java
// Đoạn minh họa phải đặt trong chương trình có Child:
for (Method method : Child.class.getDeclaredMethods()) {
    System.out.println(method.getName()
            + " bridge=" + method.isBridge()
            + " synthetic=" + method.isSynthetic());
}
```

Output **có thể khác thứ tự** vì `getDeclaredMethods()` không cam kết thứ tự phần tử. Vì thế ví dụ hoàn chỉnh ở trên đếm thay vì in toàn bộ để có stdout ổn định.

**Kiểm bằng `javap` hoặc bytecode parser** trả lời: *Trong file `.class` chứa những instruction, flags, descriptor và attributes nào?* Hai phép kiểm không thay thế cho nhau: Reflection không cho xem instruction và không trả annotation retention `CLASS` theo đường chuẩn.

## 8. Các dạng mã compiler sinh khác cần phân biệt

Bài học không giới hạn ở method synthetic. Java compiler còn có thể tạo hoặc thay đổi:

| Trường hợp | Điều compiler/JVM cần thực hiện | Cách nhìn đúng |
| --- | --- | --- |
| **Constructor mặc định** | Thêm constructor nếu lớp đủ điều kiện theo quy tắc Java | Constructor có thể có bytecode mà source không khai báo; không tự đồng nghĩa `synthetic` |
| **Enum** | Cung cấp các thành viên và cách khởi tạo theo mô hình enum | Một số method/field phụ trợ có thể do compiler sinh; đừng giả định mọi member đều có flag synthetic |
| **Record** | Sinh accessor, constructor/các method chuẩn theo quy tắc record khi không được tự khai báo | Các member công khai do ngôn ngữ yêu cầu không thể bị gạt bỏ chỉ bằng heuristic “compiler generated” |
| **Try-with-resources** | Đảm bảo đóng resource, bảo toàn primary/suppressed exceptions | Có thể sinh nhiều nhánh exception trong **cùng một method**; không nhất thiết có method phụ trợ riêng |
| **Enhanced for** | Chuyển cú pháp vòng lặp thành iterator hoặc index-based loop tùy kiểu | Nhiều lệnh bytecode hơn số câu lệnh source; source line mapping có thể không trực tiếp |
| **Nested/inner classes** | Lưu thông tin nest/outer, capture enclosing instance hoặc biến cần thiết | Fields và constructor parameters phụ trợ tùy compiler/JDK; không dựa vào tên `this$0` như API |
| **String concatenation** | Có thể dùng `invokedynamic` với `StringConcatFactory` | Không phải lambda dù opcode trùng |
| **Switch, pattern matching, assertion** | Sinh nhánh, helper hoặc cấu trúc điều khiển để bảo toàn semantics | Đánh giá theo bytecode thực, không suy từ cú pháp nguồn |

Ngoài ra các metadata như `LineNumberTable`, `LocalVariableTable`, `MethodParameters`, `Signature`, `NestHost`/`NestMembers`, `Record` có thể giúp lập bản đồ lại source, nhưng bản chất và mức độ có mặt của chúng khác nhau. `javac -g` bổ sung debug information, `javac -parameters` bổ sung tên tham số cho Reflection; không nên nhầm hai tùy chọn này với retention annotation.

## 9. Hệ quả cụ thể với công cụ instrumentation

### 9.1. Xác định đơn vị đo trước khi chọn filter

Một **logical business operation** có thể đi qua nhiều method bytecode:

```text
call site
   → generic bridge         (chuyển kiểu/forward)
       → user method        (logic nghiệp vụ)
           → lambda body    (khi được gọi)
```

Nếu bạn cần metric “mỗi lần nghiệp vụ gọi một lần”, đặt probe tại ranh giới đã chọn và tránh ghi cùng sự kiện ở mọi tầng. Nếu cần trace chi tiết bytecode, có thể quan sát cả bridge và lambda, nhưng phải mô tả rõ chúng là những frame/tầng lồng nhau, không phải các hoạt động độc lập.

Bộ lọc khởi đầu thường gồm: bỏ bridge khỏi một số loại metric, chỉ chọn synthetic method có vai trò cụ thể, tránh package nội bộ của agent, giữ blacklist/allowlist theo class loader. Đây là **chính sách tùy mục tiêu**, không phải định luật “mọi bridge/synthetic đều bỏ”.

### 9.2. Dùng flag thực từ class file, không đoán theo tên

Với thư viện đọc class file, công cụ có thể kiểm tra các bit tương ứng như `ACC_BRIDGE` và `ACC_SYNTHETIC`; với Reflection có `Method.isBridge()` và `Method.isSynthetic()`. Khi biến đổi bytecode, dùng descriptor thực (kiểu bị xóa) và thông tin generic `Signature` đúng vai trò. Chỉ match theo tên `convert` có thể chọn cả bridge lẫn override; chỉ match `(String)->String` có thể bỏ sót lời gọi ở ranh giới erased method.

Tương tự, `lambda$` là dấu hiệu gợi ý của `javac`, không phải tiêu chuẩn để xác định tất cả lambda. Bootstrap method owner và method handles ở call site cung cấp thông tin tốt hơn cho phân tích bytecode, nhưng runtime có thể dùng nhiều phương án hiện thực.

### 9.3. Annotation: đọc đúng lớp metadata

Agent hoạt động trên `ClassFileTransformer` có thể đọc annotation retention `CLASS` và `RUNTIME` từ bytecode gốc. Một interceptor chỉ dựa vào Reflection thường thấy annotation `RUNTIME`. Với type-use annotation, phải tìm đúng thuộc tính `...TypeAnnotations` thay vì lấy annotation của declaration.

Không mặc định annotation trên bridge giống method override. Một số compiler có thể sao chép annotation sang bridge hoặc generate metadata theo cách riêng; kiểm tra artifact thực trước khi xây rule. Nếu agent tự thêm annotation, phải cân nhắc framework có thể đọc nó ở đâu và như thế nào.

### 9.4. Lambda và asynchronous work

Instrumenting `invokedynamic` nơi tạo callback khác với instrumenting phần thân callback lúc chạy. Ví dụ một callback được tạo trong HTTP request A nhưng chạy trên executor sau đó; nếu chỉ capture context ở creation mà không propagation/cơ chế thực thi phù hợp, span có thể bị nối sai cha. Hãy chọn ranh giới submit/start/complete tùy ngữ nghĩa cần đo và thư viện quan sát đang dùng.

Nếu runtime tạo hidden classes, transformer không nên giả định có thể tự do retransform từng implementation. Khi muốn quan sát toàn bộ callback, lựa chọn khác là instrument ranh giới executor, framework callback hoặc những method hiện hữu có contract ổn định.

### 9.5. Đúng bytecode và giữ semantics

Chèn mã trong method phải giữ đúng thứ tự và kết quả của return/throw, exception table, verifier stack map frames, local variables, class-file version và thông tin cần thiết khác. Không được vô tình đổi bridge thành method public hiển thị như API mới, loại annotation bắt buộc của framework, hoặc làm mất generic signature.

Với bytecode transformer sản xuất thực tế, nên dùng thư viện như ASM hoặc Byte Buddy để quản lý cấu trúc bytecode và kiểm tra các phiên bản JVM mục tiêu. Sau biến đổi, kiểm tra class có load được, code chạy đúng, lỗi không bị nuốt, stack trace/line number vẫn hữu ích và overhead của probe chấp nhận được.

## 10. Quy trình điều tra một method “lạ” khi đang instrument

**Bước 1 — Nhìn runtime/source context.** Ghi lại JDK, compiler, target release, tên class, class loader, method descriptor và call path. Cùng tên nhưng khác descriptor là các method khác nhau.

**Bước 2 — Xem class file.** Dùng `javap -v -p` để xem flags (`ACC_SYNTHETIC`, `ACC_BRIDGE`), descriptor, `Signature`, annotation attributes, `BootstrapMethods`. Dùng `javap -c -p` để xem instruction và method nào thật sự gọi method nào.

**Bước 3 — So Reflection.** `Method.isBridge()`/`isSynthetic()` cho biết flag nhìn thấy qua Reflection; `isAnnotationPresent(...)` chỉ kiểm tra metadata runtime theo API phù hợp. Đừng suy ra CLASS-retention annotation đã biến mất chỉ vì Reflection trả false.

**Bước 4 — Xác định điểm đo.** Muốn đếm logical request, đo boundary ổn định. Muốn chẩn đoán generics dispatch, quan sát bridge. Muốn đo thời gian callback, đo invocation thay vì chỉ lambda creation.

**Bước 5 — Kiểm tra trước/sau.** Chạy cùng đầu vào có và không có agent; so kết quả, ngoại lệ, số lần gọi, số span/metric và thời gian. Kiểm tra cả nhánh lỗi, overload, generic raw call, concurrent callbacks và class loading khác nhau nếu chúng thuộc phạm vi áp dụng.

## 11. Những nhầm lẫn thường gặp

1. **“Mọi annotation đều dùng được bằng Reflection.”** Sai. `SOURCE` không giữ vào class file; `CLASS` không được Reflection thông thường trả; `RUNTIME` mới có retention phù hợp cho runtime lookup.
2. **“Annotation trực tiếp chèn hành vi vào method.”** Sai. Metadata không tự chạy. Cần processor, framework, transformer hoặc runtime component chủ động xử lý.
3. **“Synthetic nghĩa là dead code.”** Sai. Synthetic method có thể là phần thân lambda hoặc thành phần cần thiết để chương trình chạy đúng.
4. **“Bridge chỉ là một overload viết thừa.”** Sai. Nó bảo toàn overriding và dispatch sau erasure hoặc khi thay đổi return type tương thích.
5. **“Đếm method entry bằng tổng số nghiệp vụ.”** Chưa chắc. Bridge và các wrapper/proxy có thể làm một logical call đi qua nhiều frame.
6. **“Mọi lambda sinh class file nằm sẵn trong JAR.”** Sai. Một phần implementation được tạo/liên kết lúc chạy; hidden class có thể xuất hiện.
7. **“Có `invokedynamic` thì chắc chắn là lambda.”** Sai. Nhiều tính năng sử dụng `invokedynamic`; phải kiểm tra bootstrap.
8. **“Tên `lambda$main$0` luôn tồn tại và ổn định.”** Sai. Đây là chi tiết compiler, không phải hợp đồng chuẩn.
9. **“Đã có `Signature` generic nên JVM dispatch theo generic type.”** Sai. JVM liên kết method dựa trên descriptor đã erasure; `Signature` giữ thông tin generic cho công cụ/API liên quan.
10. **“Lọc hết bridge và synthetic là luôn tối ưu.”** Sai. Điều đó có thể hợp với một metric ở mức nghiệp vụ, nhưng gây thiếu dữ liệu khi phân tích chính bridge hoặc lambda.

## 12. Tự kiểm tra

**Câu 1:** `@Retention(CLASS)` được `javap` nhìn thấy nhưng `isAnnotationPresent` trả `false`. Có mâu thuẫn không?  
**Đáp:** Không. Metadata ở class file không đồng nghĩa Reflection runtime phải trả nó.

**Câu 2:** Vì sao `Parent<String>.convert` và `Child.convert(String)` có thể cần thêm `Child.convert(Object)`?  
**Đáp:** Generic erasure làm `Parent.convert` có descriptor nhận/trả `Object`; bridge bảo toàn dispatch tới override nhận/trả `String`.

**Câu 3:** Có nên bỏ mọi method `synthetic` khỏi trace?  
**Đáp:** Tùy mục tiêu. Tránh double-count bridge cho metric nghiệp vụ có thể hợp lý, nhưng synthetic lambda body vẫn có thể chứa logic cần chẩn đoán.

**Câu 4:** Lambda được tạo lúc 10:00 nhưng callback chạy lúc 10:05. Probe ở `invokedynamic` đo điều gì?  
**Đáp:** Nó quan sát hoạt động liên kết/capture khi đánh giá biểu thức; không mặc nhiên đo thời gian body chạy lúc 10:05.

**Câu 5:** Tại sao không dựa hoàn toàn vào `lambda$` hoặc `$$Lambda` khi thiết kế agent?  
**Đáp:** Các tên và cách sinh implementation không ổn định giữa compiler/JDK; method reference thậm chí có thể trỏ tới method hiện hữu.

## Tài liệu tham khảo

- [The Java Virtual Machine Specification, Java SE 21 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): method flags, descriptors, attributes, annotation và bootstrap methods.
- [JDK 21 — `RetentionPolicy`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/RetentionPolicy.html): định nghĩa `SOURCE`, `CLASS`, `RUNTIME`.
- [JDK 21 — `Method.isBridge()` và `Method.isSynthetic()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): API Reflection trên method.
- [JDK 21 — `LambdaMetafactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): call site, linkage, capture và invocation.
- [JDK 21 — `javap`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): xem bytecode, flags và attributes.

**Ghi nhớ:** Source code mô tả ý định của lập trình viên; class file chứa cả metadata và cấu trúc trợ giúp để JVM thực hiện ý định đó. Instrumentation đúng phải phân biệt annotation với code, bridge với method thực, synthetic với code không cần thiết, và lambda creation với lambda invocation.