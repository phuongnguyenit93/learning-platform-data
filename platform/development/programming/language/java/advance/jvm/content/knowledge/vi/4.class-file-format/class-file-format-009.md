# Signature, annotation, synthetic và bridge: dữ liệu bổ sung ngoài descriptor của ClassFile

Một tệp `.class` không chỉ chứa bytecode và **descriptor** của field/method. Nó còn có các **attribute**, cờ truy cập và metadata giúp trình biên dịch, công cụ phân tích, thư viện reflection và framework hiểu thêm thông tin ở cấp ngôn ngữ Java. Bốn khái niệm quan trọng trong nhóm này là **`Signature`**, **annotation**, **`synthetic`** và **bridge method**.

Các thông tin này liên quan nhưng không đồng nhất:

- **Descriptor** là biểu diễn kiểu ở mức JVM để mô tả field hoặc danh sách tham số và kiểu trả về của method. Nó phục vụ cấu trúc ClassFile, kiểm tra kiểu và liên kết lời gọi ở runtime.
- **`Signature` attribute** bổ sung mô tả kiểu generic: tham số kiểu `<T>`, giới hạn kiểu, tham số hóa như `List<String>`, wildcards và quan hệ `implements Interface<String>`. Descriptor thường chỉ giữ kiểu sau **type erasure**.
- **Annotation attributes** lưu những annotation mà compiler quyết định ghi vào class file theo retention/target, bao gồm cả annotation có thể được Java reflection đọc tại runtime.
- **`ACC_SYNTHETIC`** đánh dấu thành phần được tạo bởi công cụ và không xuất hiện như khai báo tương ứng trực tiếp trong nguồn; **`ACC_BRIDGE`** đánh dấu method mang chức năng bridge. Nhiều bridge method do `javac` tạo có **cả hai cờ**, nhưng hai khái niệm không đồng nghĩa.

Bài này nằm trong chủ đề **tệp class**: điều cần hiểu là metadata được lưu ở đâu, dùng để làm gì và khác dữ liệu mà JVM trực tiếp cần khi thực thi ra sao. Các ví dụ sử dụng JDK **17 trở lên**; chi tiết bytecode và thứ tự constant pool có thể khác giữa compiler.

## 1. Descriptor trả lời câu hỏi gì?

Trong ClassFile, `field_info` và `method_info` tham chiếu tới **field descriptor** hoặc **method descriptor** bằng các mục trong constant pool. Một số ký hiệu thường gặp:

| Kiểu Java | Descriptor tương ứng |
| --- | --- |
| `int` | `I` |
| `boolean` | `Z` |
| `long` | `J` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `List` | `Ljava/util/List;` |
| `void` khi là kết quả method | `V` |

Method descriptor có dạng `(tham_so_1tham_so_2...)kieu_tra_ve`:

```text
Java:       int sum(int a, long b)
Descriptor: (IJ)I

Java:       String get()
Descriptor: ()Ljava/lang/String;

Java:       void accept(String[] values)
Descriptor: ([Ljava/lang/String;)V
```

Descriptor dùng **tên nội bộ** với dấu `/` như `java/lang/String`, không phải dấu `.` theo cú pháp mã Java. Nó không lưu đầy đủ các kiểu generic được viết trong source. Ví dụ cả `List<String>` và `List<Integer>` đều có **raw descriptor** `Ljava/util/List;`; JVM vẫn phân biệt field theo tên và descriptor chứ không phân biệt hai tham số generic trong descriptor này.

Với method, **kiểu trả về cũng là một phần của JVM method descriptor**. Đây là khác biệt cần nhớ so với quy tắc overload ở Java source, nơi không được chỉ tạo hai method trùng tên và cùng tham số mà chỉ khác kiểu trả về.

## 2. `Signature`: lưu lại thông tin generic sau type erasure

### 2.1. Vì sao cần một thuộc tính riêng?

Java generics giúp `javac` kiểm tra kiểu tĩnh, nhưng cơ chế JVM truyền thống chạy với những descriptor đã được **erasure**. Mã:

```java
java.util.List<String> names;
```

có thể được biểu diễn trong ClassFile bằng:

```text
descriptor: Ljava/util/List;
Signature:  Ljava/util/List<Ljava/lang/String;>;
```

Các dòng này minh họa thông tin có thể thấy bằng `javap -v`, không phải một chương trình Java độc lập.

Descriptor `Ljava/util/List;` cho biết kiểu reference mà runtime xử lý. `Signature` giữ lại thông tin **tham số hóa bằng `String`** để công cụ/reflective API có thể phân tích. Nếu chỉ đọc descriptor, bạn không thể biết field nguồn khai báo `List<String>` hay `List<Integer>`.

### 2.2. `Signature` có thể gắn ở đâu?

Trong ClassFile, `Signature` là một attribute có thể xuất hiện ở **class**, **field** và **method** khi cần ghi generic signature.

| Nơi xuất hiện | Ví dụ Java nguồn | Nội dung generic mà `Signature` có thể bảo lưu |
| --- | --- | --- |
| Class | `class Box<T> {}` | Khai báo type parameter `T`, bound của nó, lớp cha/interface generic |
| Field | `List<String> names;` | Tham số kiểu `String` của trường |
| Method | `<T> T identity(T input)` | Type parameter của method, tham số, kết quả và thrown types generic khi liên quan |

Ví dụ ở cấp class:

```java
class TextBox implements java.util.function.Supplier<String> {
    @Override
    public String get() {
        return "hello";
    }
}
```

Class này có thể mang `Signature` cho quan hệ `implements Supplier<String>`, dù descriptor ở method thực thi là `()Ljava/lang/String;`. Nếu một method có tham số kiểu `T`, erasure thường thay `T` bằng bound phù hợp, mặc định `Object` khi không có bound chặt hơn.

### 2.3. Cách đọc generic signature

Một vài biểu thức thường gặp:

| Java source | Biểu diễn signature minh họa |
| --- | --- |
| `List<String>` | `Ljava/util/List<Ljava/lang/String;>;` |
| `List<? extends Number>` | `Ljava/util/List<+Ljava/lang/Number;>;` |
| `List<? super Integer>` | `Ljava/util/List<-Ljava/lang/Integer;>;` |
| `List<?>` | `Ljava/util/List<*>;` |
| Type variable `T` | `TT;` |

Các ký hiệu `+`, `-`, `*`, `T...;` thuộc **ngữ pháp generic signature**, không phải bytecode instruction để cộng, trừ hoặc nhân.

**Giới hạn quan trọng:** `Signature` bổ sung metadata để công cụ hiểu **khai báo kiểu generic**; bản thân nó không biến `List<String>` và `List<Integer>` thành hai runtime class khác nhau. Cơ chế kiểm tra và chuyển kiểu của Java generics chịu ảnh hưởng type erasure; ví dụ sau khi lấy phần tử qua một giao diện generic đã erase, compiler có thể sinh `checkcast`.

### 2.4. Khi thiếu hoặc hỏng `Signature`

Không phải mọi class, field, method đều có `Signature`: một khai báo không có thông tin generic cần bảo lưu có thể chỉ cần descriptor. Các thư viện reflection có API đọc kiểu thô (`Field.getType`, `Method.getReturnType`) và API đọc kiểu generic (`Field.getGenericType`, `Method.getGenericReturnType`, `Class.getGenericInterfaces`). API generic có thể đọc attribute `Signature` khi có.

Với class file được sửa bằng bytecode tool, `Signature` không hợp lệ có thể khiến một số thao tác generic reflection ném lỗi như `GenericSignatureFormatError` hoặc `TypeNotPresentException`; điều này khác với kết luận “mọi method đều cần `Signature` để JVM gọi được”.

## 3. Annotation: metadata được lưu thành attribute

Annotation trong Java được khai báo bằng `@interface` và có thể gắn vào class, field, method, parameter, type use... tùy `@Target`. ClassFile có các attribute cho nhiều loại annotation:

| Attribute thường gặp | Vai trò |
| --- | --- |
| `RuntimeVisibleAnnotations` | Annotation tại các declaration được lưu để có thể quan sát qua các API reflection tương ứng |
| `RuntimeInvisibleAnnotations` | Annotation được giữ trong class file nhưng thường **không** được Java reflection trực tiếp trả về |
| `RuntimeVisibleParameterAnnotations`, `RuntimeInvisibleParameterAnnotations` | Annotation gắn vào tham số được đánh chỉ số theo cấu trúc method |
| `RuntimeVisibleTypeAnnotations`, `RuntimeInvisibleTypeAnnotations` | Annotation tại **type use** hoặc type parameter/bound với vị trí được mã hóa trong class file |
| `AnnotationDefault` | Giá trị mặc định của một phần tử trong **annotation type** |

Các thuộc tính này được mã hóa theo cấu trúc dữ liệu của JVM (constant pool references, element-value pairs, target/path của type annotation...). Chúng **không phải** đoạn văn `@MyAnnotation(...)` được chèn nguyên xi vào bytecode.

### 3.1. Retention quyết định annotation tồn tại tới giai đoạn nào

| `@Retention` | Sau khi biên dịch | Java reflection thông thường |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Compiler bỏ annotation theo chính sách SOURCE; không ghi thành annotation tương ứng trong ClassFile | Không thấy |
| `RetentionPolicy.CLASS` | Được ghi vào class file; thường dưới dạng runtime-invisible annotation | Không thấy qua API đọc annotation thông thường |
| `RetentionPolicy.RUNTIME` | Được ghi thành metadata có thể truy vấn ở runtime | Có thể đọc theo vị trí và API phù hợp |

Nếu một annotation type **không khai báo `@Retention`**, mặc định là **`CLASS`**. `@Target` giới hạn nơi dùng annotation (khai báo class, method, parameter, `TYPE_USE`...), **không** tự quy định retention.

Đừng suy luận rằng mọi annotation có `RUNTIME` đều hiển thị qua cùng một lệnh reflection: declaration annotations và type-use annotations dùng các API khác nhau. Việc inherited annotations cũng có quy tắc riêng; `@Inherited` chỉ có tác dụng cho một số cách tra cứu annotation trên **class**, không tự làm method/field annotation kế thừa tùy ý.

### 3.2. `AnnotationDefault` không phải giá trị object runtime

Ví dụ:

```java
@interface Status {
    String value() default "new";
}
```

Giá trị `"new"` được ghi thành `AnnotationDefault` trên **method biểu thị phần tử `value` của annotation type**. Nó không đòi mỗi lần sử dụng annotation phải lưu lại một bản sao giá trị mặc định. Reflection có thể tra cứu bằng `Method.getDefaultValue()`.

### 3.3. Annotation chỉ bổ sung metadata, không tự chạy nghiệp vụ

Viết `@Transactional`, `@Test`, `@Deprecated` hoặc annotation tự tạo **không mặc nhiên khiến JVM thực hiện hành động đặc biệt** mỗi khi method được gọi. Hành vi bổ sung thường do compiler, annotation processor, framework, agent hoặc tooling đọc metadata và triển khai. Một số annotation chuẩn được compiler/VM xử lý theo quy tắc cụ thể; không nên khái quát rằng mọi annotation đều thuần chú thích hoặc đều tự thực thi.

## 4. `synthetic`: dấu vết thành phần được sinh ra

Một số thành phần của class file không có khai báo Java source tương ứng theo cách thông thường, bởi compiler hoặc công cụ đã sinh thêm để hỗ trợ ngữ nghĩa chương trình. ClassFile có cờ **`ACC_SYNTHETIC`** đối với các thành phần thích hợp và, trong định dạng lịch sử, có attribute tên **`Synthetic`**. Cờ và attribute là hai hình thức biểu diễn cần phân biệt theo phiên bản class file.

Các tình huống có thể gặp:

- Một **bridge method** do compiler tạo để bảo toàn dispatch sau generic erasure hoặc hỗ trợ covariant return.
- Một method phụ trợ được compiler sinh từ một số cấu trúc ngôn ngữ, ví dụ method triển khai lambda trên một số phiên bản/chiến lược compiler.
- Một field hoặc method hỗ trợ truy cập/biểu diễn nội bộ của compiler trong những cách dịch mã nguồn nhất định.

**Không phải mọi thành phần không nhìn thấy rõ ở source đều được đánh `synthetic`.** Ví dụ constructor mặc định do compiler tạo không nhất thiết mang cờ synthetic. Java record, enum và nested class cũng có các thành phần được định nghĩa bởi đặc tả với quy tắc riêng. Cần kiểm tra flag thật trên class file, không đoán chỉ từ tên như `lambda$...` hoặc `access$...`.

Phần tử synthetic vẫn là thành phần **thực sự tồn tại trong class file** và có thể chứa bytecode được JVM gọi. Reflection có thể liệt kê nó, và API như `Method.isSynthetic()`, `Field.isSynthetic()` giúp nhận biết theo metadata. Synthetic **không đồng nghĩa** private, invisible, không thể gọi hay lỗi biên dịch.

## 5. Bridge method: tại sao descriptor đã erase cần thêm một method?

### 5.1. Vấn đề phát sinh khi dùng generics

Xét interface và class:

```java
interface Provider<T> {
    T get();
}

class StringProvider implements Provider<String> {
    @Override
    public String get() {
        return "OK";
    }
}
```

Đây là **đoạn minh họa**, cần đặt vào tệp phù hợp mới biên dịch. Ở Java source, `StringProvider.get()` thực hiện hợp đồng `Provider<String>.get()`. Nhưng sau type erasure:

```text
Provider<T>.get()            → method descriptor: ()Ljava/lang/Object;
StringProvider.get()         → method descriptor: ()Ljava/lang/String;
```

Tại cấp JVM, hai descriptor **khác nhau về kiểu trả về**. Để một lời gọi qua `Provider` vẫn tìm đúng implementation sau erasure, `javac` có thể sinh thêm vào `StringProvider` method đại loại:

```java
// Pseudocode diễn giải mục đích, KHÔNG được chép vào class nguồn.
// Do compiler sinh thành bytecode trong StringProvider:
public Object get() {
    return this.get(); // gọi bản get() trả về String
}
```

Đây **không phải Java source hợp lệ** khi đặt cùng `String get()` trong class vì Java không overload chỉ theo return type. Trong **ClassFile**, hai method có descriptor khác nhau và method trả về `Object` được compiler đánh dấu **`ACC_BRIDGE`**, thông thường đồng thời có **`ACC_SYNTHETIC`**. Bridge chuyển tiếp lời gọi tới implementation chính, giúp polymorphism hoạt động đúng.

Ở mức bytecode minh họa:

```text
StringProvider.get():Ljava/lang/String;   // method gốc
StringProvider.get():Ljava/lang/Object;   // method bridge
    aload_0
    invokevirtual StringProvider.get:()Ljava/lang/String;
    areturn
```

Chỉ số constant pool và offset của từng instruction tùy kết quả `javap` thực tế.

### 5.2. Bridge không chỉ gắn với `T` của generic

Java cho phép **covariant return type** trong override (method con trả kiểu reference cụ thể hơn). Ví dụ:

```java
class Parent {
    Object value() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    String value() {
        return "child";
    }
}
```

Trong các bản dịch cần tương thích với lời gọi qua descriptor của `Parent.value():Object`, compiler có thể tạo method bridge trên `Child`. **Không nên suy ra cứ có bridge thì source nhất định khai báo generic.** Điều kiện và cách sinh bridge là việc compiler bảo đảm ngữ nghĩa dispatch/binary compatibility phù hợp.

### 5.3. `ACC_BRIDGE` và `ACC_SYNTHETIC` khác nhau

| Trường/cờ | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| `ACC_BRIDGE` | Method có vai trò bridge do compiler tạo | `Method.isBridge()`, `javap -v` |
| `ACC_SYNTHETIC` | Thành phần synthetic, không tương ứng một khai báo source thông thường | `Member.isSynthetic()` trên các member phù hợp, `javap -v` |
| `Signature` | Metadata mô tả generic signature | `javap -v`, API generic reflection |
| `RuntimeVisibleAnnotations` | Annotation có thể xem được ở runtime theo API thích hợp | `javap -v`, Java reflection |

Cờ `ACC_BRIDGE` chỉ có ý nghĩa cho **method**, không phải field hay class. Một bridge thường là synthetic, nhưng **synthetic method chưa chắc là bridge**; `Method.isSynthetic()` một mình không xác định được mục đích của method.

## 6. Thực hành hoàn chỉnh Java 17+: quan sát cả bốn khái niệm

Tạo file **`ClassMetadataDemo.java`**, lưu UTF-8:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

public class ClassMetadataDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface RuntimeTag {
        String value() default "default";
    }

    @Retention(RetentionPolicy.CLASS)
    @Target(ElementType.TYPE)
    @interface ClassTag {}

    @Retention(RetentionPolicy.SOURCE)
    @Target(ElementType.TYPE)
    @interface SourceTag {}

    interface Provider<T> {
        T get();
    }

    @RuntimeTag("demo")
    @ClassTag
    @SourceTag
    static final class TextProvider implements Provider<String> {
        @Override
        public String get() {
            return "xin chào";
        }
    }

    static final class Holder {
        List<String> names = List.of("An", "Bình");
    }

    public static void main(String[] args) throws Exception {
        Field names = Holder.class.getDeclaredField("names");
        System.out.println("raw field: " + names.getType().getTypeName());
        System.out.println("generic field: "
                + names.getGenericType().getTypeName());

        RuntimeTag tag = TextProvider.class.getAnnotation(RuntimeTag.class);
        System.out.println("runtime annotation: " + tag.value());
        System.out.println("annotation default: "
                + RuntimeTag.class.getDeclaredMethod("value").getDefaultValue());
        System.out.println("class-retention via reflection: "
                + TextProvider.class.isAnnotationPresent(ClassTag.class));
        System.out.println("source-retention via reflection: "
                + TextProvider.class.isAnnotationPresent(SourceTag.class));

        int bridges = 0;
        boolean bridgeIsSynthetic = false;
        for (Method method : TextProvider.class.getDeclaredMethods()) {
            if (method.isBridge()) {
                bridges++;
                bridgeIsSynthetic = method.isSynthetic();
            }
        }
        System.out.println("bridge methods: " + bridges);
        System.out.println("bridge is synthetic: " + bridgeIsSynthetic);

        Provider<String> provider = new TextProvider();
        System.out.println("interface dispatch: " + provider.get());
    }
}
```

Trong terminal ở thư mục chứa file:

```bash
mkdir out
javac -encoding UTF-8 -d out ClassMetadataDemo.java
java -cp out ClassMetadataDemo
```

**Standard output dự kiến từ `javac` JDK 17+ thông thường:**

```text
raw field: java.util.List
generic field: java.util.List<java.lang.String>
runtime annotation: demo
annotation default: default
class-retention via reflection: false
source-retention via reflection: false
bridge methods: 1
bridge is synthetic: true
interface dispatch: xin chào
```

Giải thích chính xác từng phần:

1. `names.getType()` trả kiểu thô của field, tương ứng descriptor `Ljava/util/List;`.
2. `names.getGenericType()` đọc thông tin generic `List<String>` được bảo lưu trong `Signature`.
3. `RuntimeTag` là declaration annotation được đánh retention `RUNTIME`, nên `getAnnotation` có thể trả về instance annotation; `value()` trả `"demo"`.
4. Giá trị `"default"` của phần tử annotation được chứa qua `AnnotationDefault` trong annotation type. Giá trị được ghi khi sử dụng `@RuntimeTag("demo")` là `"demo"`, nên không nhầm hai nguồn giá trị.
5. `ClassTag` có retention `CLASS`: có thể quan sát trong ClassFile bằng công cụ đọc metadata nhưng **không** xuất hiện qua `isAnnotationPresent` thông thường. `SourceTag` chỉ tồn tại ở giai đoạn xử lý source.
6. `TextProvider` cung cấp `String get()`, trong khi `Provider<T>.get()` có descriptor sau erasure trả `Object`. Compiler tạo một **bridge method** `Object get()` để lời gọi qua interface vẫn dispatch đúng, và bridge này thường có cả cờ synthetic.
7. Biến `provider` có kiểu `Provider<String>`; gọi `provider.get()` thông qua interface vẫn trả chuỗi `"xin chào"`.

Kết quả có chữ tiếng Việt phụ thuộc terminal hiển thị UTF-8 đúng; file được yêu cầu biên dịch bằng `-encoding UTF-8` để xác định encoding của nguồn.

### 6.1. Dùng `javap -v` để xem các thành phần thật

Sau khi biên dịch, chạy:

```bash
javap -classpath out -v -p ClassMetadataDemo
javap -classpath out -v -p 'ClassMetadataDemo$Holder'
javap -classpath out -v -p 'ClassMetadataDemo$TextProvider'
javap -classpath out -v -p 'ClassMetadataDemo$RuntimeTag'
```

Các dấu nháy đơn cho tên nested class phù hợp với shell Bash và PowerShell; nếu dùng Windows `cmd.exe`, có thể thay chúng bằng dấu nháy kép để bảo vệ ký tự `$`. Tên file/class chính là `ClassMetadataDemo`; các nested types có tên nhị phân chứa `$`.

**Ở `ClassMetadataDemo$Holder`**, tìm thông tin đại loại:

```text
java.util.List<java.lang.String> names;
  descriptor: Ljava/util/List;
  Signature: ... // Ljava/util/List<Ljava/lang/String;>;
```

Các ký hiệu `...` ở đây là **phần output minh họa đã lược bỏ chỉ số constant pool**, không phải dòng output chính xác để so sánh từng ký tự. Mấu chốt là `descriptor` biểu diễn raw `List`, còn `Signature` giữ `<String>`.

**Ở `ClassMetadataDemo$TextProvider`**, tìm cả hai method `get`:

```text
public java.lang.String get();
  descriptor: ()Ljava/lang/String;
  flags: ... ACC_PUBLIC ...

public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
  flags: ... ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC ...
```

Đây là **trích mô tả những dòng cần đối chiếu**, không sao chép nguyên một listing `javap`. Có thể thấy thêm `Signature` của class cho `Provider<String>`, `RuntimeVisibleAnnotations` cho `RuntimeTag` và `RuntimeInvisibleAnnotations` cho `ClassTag`. `SourceTag` không được giữ thành annotation trong class file.

**Ở `ClassMetadataDemo$RuntimeTag`**, tìm `AnnotationDefault` của phần tử `value`; có thể đọc nội dung `default_value: s#...` với một mục constant pool tương ứng chuỗi `"default"`.

### 6.2. Nhìn bytecode bridge

```bash
javap -classpath out -c -p 'ClassMetadataDemo$TextProvider'
```

Trong method bridge trả `Object`, `javap -c` thường thể hiện mẫu hành vi tương đương:

```text
aload_0
invokevirtual ... get:()Ljava/lang/String;
areturn
```

Ý nghĩa:

- `aload_0` đưa reference `this` lên operand stack.
- `invokevirtual` gọi method implementation thực sự `get():String`.
- `areturn` trả reference `String` dưới kiểu trả về JVM `Object` của bridge.

`String` là subtype của `Object`, nên bytecode có thể trả chính tham chiếu đó mà không sao chép đối tượng. Trong các tình huống override với tham số generic, bridge còn có thể cần `checkcast` trước khi ủy quyền, vì kiểu tham số cũng bị erasure. Không mặc định mọi bridge có cùng ba lệnh trên.

## 7. Reflection nhìn thấy bao nhiêu metadata?

Java reflection cho phép đọc **một phần metadata được ghi trong class file**, không cho phép phục dựng hoàn toàn source Java ban đầu.

| Nhu cầu | API ví dụ | Dữ liệu đọc |
| --- | --- | --- |
| Kiểu thô của field | `Field.getType()` | Class đại diện kiểu đã erase |
| Kiểu generic của field | `Field.getGenericType()` | `Type`, có thể dựa trên `Signature` |
| Kiểu trả về thô | `Method.getReturnType()` | `Class<?>` |
| Kiểu trả về generic | `Method.getGenericReturnType()` | `Type` |
| Tham số kiểu của class | `Class.getTypeParameters()` | `TypeVariable<?>[]` |
| Các generic interfaces | `Class.getGenericInterfaces()` | `Type[]` |
| Annotation runtime của class | `Class.getAnnotation(...)` | Annotation nhìn thấy theo retention/API |
| Giá trị mặc định của annotation element | `Method.getDefaultValue()` | Giá trị `AnnotationDefault` |
| Method có phải bridge không? | `Method.isBridge()` | Cờ `ACC_BRIDGE` |
| Method có synthetic không? | `Method.isSynthetic()` | Metadata synthetic |
| Type-use annotations | Các API `AnnotatedType` thích hợp | Metadata type annotation runtime mà API hỗ trợ |

**Giới hạn của reflection:** `RetentionPolicy.CLASS` được thiết kế để có thể lưu trong class file nhưng không được trả như runtime-visible annotation bởi API reflection tiêu chuẩn. Muốn phân tích loại thông tin đó, cần công cụ đọc ClassFile như `javap` hoặc thư viện bytecode. Một số tên biến cục bộ, thông tin gỡ lỗi hoặc generic metadata có thể không có tùy compiler flags và cấu trúc đầu vào.

Khi reflection liệt kê `getDeclaredMethods()`, bạn có thể thấy **bridge/synthetic methods**, khiến số method lớn hơn số khai báo method trong source. Framework quét method nên có quy tắc xử lý bridge nếu nó cần định danh method triển khai logic, tránh gọi/đăng ký hai lần ngoài ý muốn. Tuy nhiên không nên **xóa tất cả synthetic** một cách mù quáng: synthetic không đồng nghĩa “không có tác dụng runtime”.

## 8. Những nhầm lẫn thường gặp

| Hiểu nhầm | Cách hiểu chính xác |
| --- | --- |
| “Descriptor của `List<String>` chứa `String`.” | Descriptor thường chỉ có `Ljava/util/List;`; thông tin generic nằm trong `Signature` khi được bảo lưu |
| “`Signature` tự ngăn mọi việc đưa `Integer` vào raw `List` tại runtime.” | Kiểm tra generic chủ yếu diễn ra khi compile; erasure và các `checkcast` thích hợp giúp bảo vệ ngữ nghĩa tại nơi dùng |
| “Mọi annotation trong `.class` đều đọc được qua reflection.” | `CLASS` retention có thể lưu trong class file nhưng không được reflection thông thường hiển thị |
| “Nếu không ghi `@Retention`, annotation mặc định là `RUNTIME`.” | Mặc định là `CLASS` |
| “`@Target` quyết định annotation còn tồn tại ở runtime.” | `@Target` giới hạn vị trí dùng; `@Retention` xác định mức lưu giữ |
| “`synthetic` nghĩa là không thực thi.” | Synthetic method có thể chứa bytecode thực sự được gọi, ví dụ bridge |
| “Mọi synthetic method là bridge.” | Bridge chỉ là một trường hợp của method được sinh; phải kiểm tra `isBridge()` |
| “Bridge chỉ xuất hiện khi lập trình generic.” | Covariant return type cũng có thể làm compiler tạo bridge |
| “JVM không thể có hai method cùng tên và cùng tham số mà khác kiểu trả về.” | Ở ClassFile, method descriptor **có kiểu trả về**, nên compiler có thể sinh bridge khác descriptor; Java source không overload kiểu này |
| “`javap -v` luôn tái tạo chính xác file `.java` ban đầu.” | Nó hiển thị bytecode và metadata có trong `.class`, không phục dựng source đã mất |

## 9. Bài tập phân tích ClassFile

### Bài tập 1 — Kiểm tra `Signature` trên field

Trong ví dụ, thay `List<String> names` bằng:

```java
List<? extends Number> names;
```

Đây là **dòng thay thế trong nested class `Holder`**, không phải một class độc lập. Vì field initializer `List.of("An", "Bình")` không còn đúng kiểu, hãy thay bằng `List.of(1, 2)`. Biên dịch lại và quan sát: descriptor vẫn là `Ljava/util/List;`, còn generic signature thay đổi để thể hiện wildcard `? extends Number`. Trước khi sửa, đọc kỹ khác biệt giữa **raw JVM type** và **generic declaration**.

### Bài tập 2 — Đổi `@Retention`

Thay `@Retention(RetentionPolicy.CLASS)` của `ClassTag` thành `RUNTIME`, biên dịch và chạy lại. Dòng:

```text
class-retention via reflection: true
```

sẽ xuất hiện dù tên thông báo trong chương trình vẫn giữ nguyên. Dùng `javap -v` để quan sát annotation của class được chuyển sang nhóm runtime-visible. Đổi về `CLASS` để giữ nguyên ví dụ ban đầu.

### Bài tập 3 — Kiểm tra bridge khi đổi kiểu trả về

Trong `TextProvider`, tên method `get` giữ nguyên và trả `String` là một phần thực hiện `Provider<String>`. Mở `javap -v -p` rồi tự trả lời:

1. Method nguồn `get():String` có descriptor nào?
2. Method bridge `get():Object` có descriptor nào?
3. Method nào có `ACC_BRIDGE` và `ACC_SYNTHETIC`?
4. Khi gọi `Provider<String> p = new TextProvider(); p.get()`, vì sao kết quả vẫn là `String` hợp lệ?

### Câu hỏi tự kiểm tra

**1. Vì sao cần `Signature` khi descriptor đã có?**  
Descriptor cho biết kiểu JVM cần để tổ chức/kiểm tra lời gọi; `Signature` giữ metadata generic phong phú hơn sau erasure cho compiler và tooling.

**2. Một annotation `RetentionPolicy.CLASS` có thể tồn tại trong class file nhưng `getAnnotation` trả `null`?**  
Có. Nó thuộc nhóm runtime-invisible annotation theo các quy tắc lưu trữ thích hợp.

**3. `ACC_SYNTHETIC` và `ACC_BRIDGE` có phải một cờ?**  
Không. Cờ synthetic đánh dấu nguồn gốc kiểu compiler-generated, còn cờ bridge xác định vai trò bridge của method.

**4. Method `Object get()` bridge có phải lỗi compiler tạo trùng method không?**  
Không. Java source không cho overload chỉ bằng kiểu trả về, nhưng JVM method descriptor bao gồm return type; compiler tạo bridge có descriptor khác để bảo đảm lời gọi polymorphic sau erasure.

**5. Annotation có tự làm JVM gọi một interceptor không?**  
Không phải theo mặc định. Hành vi framework như interceptor/proxy cần một cơ chế khác đọc và xử lý annotation.

**6. Tại sao `getDeclaredMethods()` có thể thấy nhiều method hơn source?**  
Bởi class file chứa cả method do compiler sinh, trong đó có bridge và những method synthetic khác.

Khi đọc ClassFile bằng `javap`, hãy xác định riêng **descriptor (kiểu thực thi)**, **`Signature` (generic metadata)**, **annotation attributes (metadata theo retention/vị trí)** và **flags `ACC_SYNTHETIC`/`ACC_BRIDGE` (vai trò thành phần được sinh)**. Bốn nhóm giải thích vì sao JVM vẫn thực thi theo type erasure, trong khi reflection/công cụ có thể quan sát thêm generic declaration, annotation và các method không hiển thị thành khai báo Java source thông thường.