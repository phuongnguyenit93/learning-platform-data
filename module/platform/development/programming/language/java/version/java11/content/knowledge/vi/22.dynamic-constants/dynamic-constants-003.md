# Bootstrap method, tham số tĩnh và kiểu kết quả — Hằng số động trong Java 11+

## 1. Hằng số động (CONSTANT_Dynamic) là gì?

**Dynamic class-file constant**, thường gọi là **constant dynamic** hoặc **condy**, là một mục trong *constant pool* của classfile có giá trị được tính bằng một **bootstrap method (BSM)** khi JVM **resolve** tham chiếu hằng số đó. Cơ chế này được chuẩn hóa trong **JEP 309**, có từ **Java 11** (classfile major version **55**), và vẫn áp dụng trong các JVM hiện đại.

Khác với một chuỗi literal hoặc số được ghi trực tiếp ở constant pool, mục `CONSTANT_Dynamic` **không chứa sẵn giá trị cuối**. Thay vào đó nó chứa:

- **Chỉ số bootstrap** dẫn đến một entry trong class attribute `BootstrapMethods`.
- **Tên hằng số** trong `CONSTANT_NameAndType_info`.
- **Field descriptor** chỉ ra **kiểu kết quả cần được resolve** (ví dụ `I` cho `int`; `Ljava/lang/String;` cho `String`).

JVM xác định bootstrap method handle và các **static bootstrap arguments**, gọi bootstrap, **kiểm tra giá trị trả về**, rồi ghi nhận kết quả resolution cho tham chiếu đó trong runtime constant pool.

Điểm cần hiểu rõ nhất: **bootstrap method không phải phương thức “khởi động cả chương trình”**; nó là callback phục vụ *liên kết động* một mục constant pool cụ thể.

### Mục tiêu sau bài học

1. Đọc được quan hệ giữa `CONSTANT_Dynamic`, `BootstrapMethods` và `ldc`.
2. Giải thích đúng ba tham số chuẩn của bootstrap: `MethodHandles.Lookup`, `String name`, `Class<?> type`.
3. Hiểu **static arguments** lưu ở đâu và được JVM chuẩn bị như thế nào.
4. Phân biệt **kiểu kết quả mô tả bằng field descriptor** với kiểu trả về khai báo của phương thức bootstrap.
5. Nhận biết trường hợp hợp lệ cho kiểu tham chiếu, kiểu nguyên thủy, `null` và trường hợp báo `BootstrapMethodError`.
6. Hiểu **cache resolution**, lỗi, quyền truy cập và tác động của đa luồng.
7. Tự chạy một classfile Java 11 thật chứa `CONSTANT_Dynamic` — không nhầm với việc chỉ gọi phương thức Java thông thường.

## 2. Cấu trúc classfile: từ constant pool tới bootstrap method

### 2.1. CONSTANT_Dynamic_info (tag 17)

Trong **JVMS `4.4.10**, entry có dạng:

```text
CONSTANT_Dynamic_info {
    u1 tag;                           // = 17
    u2 bootstrap_method_attr_index;   // Chỉ số 0-based trong BootstrapMethods
    u2 name_and_type_index;           // Tên + field descriptor
}
```

`bootstrap_method_attr_index` **không phải byte offset hay tên Java method**; nó là chỉ số của một mục trong mảng `bootstrap_methods` thuộc attribute cấp class.

`name_and_type_index` trỏ đến `CONSTANT_NameAndType_info`, ví dụ:

```text
Name: MESSAGE
Descriptor: Ljava/lang/String;

Name: COUNT
Descriptor: I
```

Đó là **field descriptor**, không phải **method descriptor**. Giá trị hằng số có thể thuộc kiểu nguyên thủy hoặc kiểu tham chiếu, nhưng **không có kiểu `void`**.

### 2.2. BootstrapMethods attribute

Một classfile có mục `CONSTANT_Dynamic` hoặc `CONSTANT_InvokeDynamic` phải có **đúng một** class-level attribute `BootstrapMethods`; attribute này chứa bảng bootstrap specifiers:

```text
BootstrapMethods:
  entry 0:
    bootstrap_method_ref   = MethodHandle(greeting)
    bootstrap_arguments    = ["hello:", 7]

  entry 1:
    bootstrap_method_ref   = MethodHandle(triple)
    bootstrap_arguments    = [7]

  entry 2:
    bootstrap_method_ref   = MethodHandle(wrongType)
    bootstrap_arguments    = []

  entry 3:
    bootstrap_method_ref   = MethodHandle(ConstantBootstraps.nullConstant)
    bootstrap_arguments    = []
```

**Đây là sơ đồ**, không phải bytecode syntax đầy đủ. Mỗi entry có:

```text
u2 bootstrap_method_ref;
u2 num_bootstrap_arguments;
u2 bootstrap_arguments[num_bootstrap_arguments];
```

`bootstrap_method_ref` trỏ tới `CONSTANT_MethodHandle_info`; `bootstrap_arguments` là các **chỉ số constant pool của những hằng số có thể load** (*loadable constants*). JVM sẽ resolve chúng và truyền **giá trị thực** cho bootstrap method.

Cùng một bảng `BootstrapMethods` có thể phục vụ **nhiều `CONSTANT_Dynamic`**, và các entry có thể có số lượng/kiểu static arguments khác nhau. Một classfile có thể dùng đồng thời `CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic`.

### 2.3. Dòng xử lý tổng quát

```text
Classfile major 55 (Java 11)
        |
        v
CONSTANT_Dynamic (tag 17)
    ├─ NameAndType: MESSAGE : Ljava/lang/String;
    └─ bootstrap_method_attr_index: 0
                   |
                   v
BootstrapMethods[0]
    ├─ MethodHandle -> CondyBootstrapDemo.greeting(...)
    └─ static arguments -> "hello:", 7
                   |
                   v
JVM resolution:
    (Lookup caller, "MESSAGE", String.class, "hello:", 7)
                   |
                   v
Bootstrap result: "hello:MESSAGE#7@CondyGenerated"
                   |
                   v
Kiểm tra kiểu String, cache resolution
                   |
                   v
ldc_w -> String đã resolve
```

**Giá trị từ bootstrap không bắt buộc là literal đã nằm sẵn trong classfile**. Bootstrap có thể trả một reference hoặc primitive theo kiểu đích được chỉ định. Tuy nhiên, việc tính giá trị cần tuân thủ các hạn chế bảo mật, quyền truy cập, tính quyết định và xử lý lỗi của ứng dụng.

## 3. Hợp đồng của bootstrap method cho constant dynamic

### 3.1. Ba tham số chuẩn

Dạng điển hình của một bootstrap method trên Java 11:

```java
public static Object bootstrap(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        Object... staticArgs) {
    // Tạo/tra cứu kết quả phù hợp với type.
    return /* value */;
}
```

Đây là **mảnh chữ ký minh họa**, không phải chương trình độc lập; phần `return` phải thay bằng giá trị có kiểu hợp lệ. **Ba đối số đầu do JVM cung cấp**:

| Đối số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `lookup` | Ngữ cảnh tra cứu của **class chứa tham chiếu `CONSTANT_Dynamic`**, dùng cho kiểm tra quyền khi cần | `lookup.lookupClass() == CondyGenerated.class` |
| `name` | Tên hằng số từ `CONSTANT_NameAndType` | `"MESSAGE"` |
| `type` | `Class<?>` đại diện cho **kiểu kết quả mong muốn** từ *field descriptor* | `String.class`, `int.class`, `int[].class` |
| Đối số còn lại | Những **static arguments** mà classfile đã liệt kê, theo đúng thứ tự | `"hello:"`, `7` |

**Lưu ý JVMS Java 11:** tham số đầu tiên của method handle dùng để resolve **dynamic constant** bắt buộc có kiểu `MethodHandles.Lookup`; nếu không, resolution thất bại với `BootstrapMethodError`. Mô tả trên là convention cho trường hợp thông dụng, không nên hiểu phương thức bootstrap bắt buộc khai báo chính xác mọi kiểu theo một mẫu duy nhất: lời gọi được chuẩn bị theo ngữ nghĩa `MethodHandle.invokeWithArguments`, có thể có chuyển đổi kiểu thích hợp hoặc hỗ trợ varargs handle.

Điểm khác biệt quan trọng khi so sánh với `invokedynamic`: tham số thứ ba của bootstrap cho **dynamic constant** là `Class<?>`, còn bootstrap cho **dynamic call site** nhận `MethodType` mô tả chữ ký phương thức. Không lấy một bootstrap của `invokedynamic` rồi sử dụng cho condy mà không kiểm tra cách nhận đối số và kiểu kết quả.

### 3.2. Tại sao lookup.lookupClass() không phải class khai báo bootstrap?

Với classfile `CondyGenerated` chứa `ldc_w #MESSAGE`, phương thức bootstrap có thể nằm ở class **khác**, chẳng hạn `CondyBootstrapDemo.greeting`. Nhưng `lookup` đại diện cho **class thực hiện constant-pool resolution** — tức `CondyGenerated`.

Ví dụ:

```java
public static String greeting(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        String prefix,
        int number) {

    if (type != String.class) {
        throw new IllegalArgumentException("Expected String");
    }
    return prefix + name + "#" + number
            + "@" + lookup.lookupClass().getSimpleName();
}
```

Đoạn trên là một **mảnh phương thức**, cần import `java.lang.invoke.MethodHandles`; bản đầy đủ có trong mục 8. Khi classfile chứa tên hằng số `MESSAGE`, static args `"hello:"` và `7`, nó sẽ trả:

```text
hello:MESSAGE#7@CondyGenerated
```

Không lấy `lookup.lookupClass()` làm `CondyBootstrapDemo.class` chỉ vì mã bootstrap được viết trong class đó. Khi bootstrap thực hiện lookup/private access, Java modules và khả năng truy cập thực tế vẫn phải tuân thủ quy tắc JVM; `Lookup` không phải “quyền mở mọi private member” ở bất cứ class nào.

### 3.3. Bootstrap method có bắt buộc trả Object?

**Không.** Có thể khai báo bootstrap trả `String`, `Integer` hoặc `Object`, miễn lời gọi method handle và **chuyển đổi kết quả tới kiểu hằng số** hợp lệ.

Ví dụ trong chương trình đầy đủ:

```java
public static String greeting(
        MethodHandles.Lookup lookup, String name,
        Class<?> type, String prefix, int number) {
    return prefix + name + "#" + number;
}

public static Object triple(
        MethodHandles.Lookup lookup, String name,
        Class<?> type, int base) {
    return Integer.valueOf(base * 3);
}
```

Các mảnh trên biểu diễn ý tưởng; phương thức thật ở demo có kiểm tra type và số lần gọi. Hằng số `COUNT:I` yêu cầu **`int`**, nhưng bootstrap trả `Object` chứa `Integer`, và JVM thực hiện chuyển đổi phù hợp như unboxing để đạt `int`.

Đây không phải ép kiểu không kiểm tra: nếu trả một đối tượng **không thể chuyển thành kiểu được yêu cầu**, resolution phải thất bại.

## 4. Static arguments: “tĩnh” ở đâu và truyền vào lúc nào?

### 4.1. Static không có nghĩa bắt buộc là primitive hoặc String

**Static arguments** được xác định bởi **classfile constant pool**, khác với tham số runtime mà code ứng dụng tự truyền khi gọi một phương thức Java.

Những entry có thể được dùng làm bootstrap arguments gồm các **loadable constants**, chẳng hạn:

- `CONSTANT_String`: chuỗi.
- `CONSTANT_Integer`, `CONSTANT_Long`, `CONSTANT_Float`, `CONSTANT_Double`: giá trị số, được chuyển đổi/đóng hộp thích hợp theo lời gọi method handle.
- `CONSTANT_Class`: đối tượng `Class<?>` đã resolve.
- `CONSTANT_MethodType`: `MethodType`.
- `CONSTANT_MethodHandle`: `MethodHandle`.
- **`CONSTANT_Dynamic` khác**: giá trị của một dynamic constant có thể làm **static argument** của dynamic constant tiếp theo.

Ví dụ:

```text
BootstrapMethods[0] arguments:
  #String("hello:")
  #Integer(7)
```

Với bootstrap nhận hai tham số cuối là `String prefix` và `int number`, JVM có thể truyền lần lượt `"hello:"` và `7`.

Không nhầm **“tham số tĩnh”** với `static` field của class Java. `static arguments` là thuật ngữ của classfile/BSM, không phải yêu cầu thuộc tính Java phải được khai báo `static`.

### 4.2. Thứ tự và độ dài

JVM ghép:

```text
[ lookup, name, type, staticArg0, staticArg1, ... ]
```

theo đúng **thứ tự bootstrap arguments** trong classfile. Nếu bootstrap khai báo:

```java
bootstrap(Lookup lookup, String name, Class<?> type,
          String prefix, int count)
```

mà classfile cung cấp `[7, "hello:"]` thay vì `["hello:", 7]`, chuyển đổi kiểu có thể thất bại. Nếu thiếu/thừa đối số không được method handle chấp nhận, resolution cũng không thành công.

Không tự chuyển `String` sang `int` bằng cách giả định JVM sẽ parse chuỗi “7” giúp bạn. Những chuyển đổi hợp lệ là chuyển đổi của `MethodHandle.invokeWithArguments`, không phải deserialization theo ý muốn.

### 4.3. Dynamic constant làm static argument: tính lồng nhau

Một bootstrap argument có thể là **một `CONSTANT_Dynamic` khác**. Khi resolve hằng số ngoài, JVM cần resolve các argument phụ thuộc **trước khi gọi bootstrap ngoài**.

```text
OUTER : Ljava/lang/String;
  └─ static argument -> INNER : I
       └─ bootstrap INNER -> 21
  └─ bootstrap OUTER(..., 21) -> "result:21"
```

Đây là sơ đồ khái niệm, không phải bytecode trong chương trình demo. Các phụ thuộc được resolve theo mô hình classfile, không phải do JVM tự “đánh giá expression Java” bất kỳ.

Theo **JVMS `5.4.3.6**, chu trình trực tiếp hoặc gián tiếp giữa các dynamic constants ở bootstrap arguments **không được hỗ trợ** và gây `StackOverflowError` theo quy tắc resolution. Do đó, không tạo đồ thị condy tự tham chiếu khi xây công cụ sinh classfile.

### 4.4. Không truyền một đối tượng tùy ý trực tiếp vào constant pool

Một array Java tùy ý, một instance service, connection hay object business **không thể** được chèn nguyên trạng vào `bootstrap_arguments` như literal của classfile. Constant pool chỉ chấp nhận các cấu trúc **loadable** chuẩn; bootstrap có thể **tạo/tra cứu đối tượng kết quả** khi được invoke, hoặc nhận kết quả của một dynamic constant phụ thuộc.

Nếu cần truyền dữ liệu lớn/tùy ý, cân nhắc thiết kế nguồn dữ liệu và ràng buộc classloader/caching thay vì nhét các đối tượng runtime vào classfile.

## 5. Kiểu kết quả và nguyên tắc kiểm tra của JVM

### 5.1. Type ở CONSTANT_Dynamic là field descriptor

Ví dụ:

| Entry | Descriptor | JVM cung cấp cho tham số `type` | Kiểu hợp lệ sau resolution |
| --- | --- | --- | --- |
| `MESSAGE` | `Ljava/lang/String;` | `String.class` | `String` hoặc `null` |
| `COUNT` | `I` | `int.class` | Một giá trị có thể chuyển thành `int` theo JVMS |
| `ENABLED` | `Z` | `boolean.class` | Giá trị boolean thích hợp |
| `BUFFER` | `[B` | `byte[].class` | `byte[]` hoặc `null` |
| `EMPTY` | `Ljava/lang/String;` | `String.class` | `null` được phép |

**Descriptor `V` (`void`) không hợp lệ** cho một dynamic constant vì `CONSTANT_Dynamic` dùng **field descriptor**.

JVM **không buộc** tên `COUNT` có liên hệ ngữ nghĩa nào với `int`; tên là metadata có thể dùng trong logic bootstrap. Điều kiện bắt buộc là **kiểu đích của entry** có thể nhận giá trị do bootstrap trả theo quy tắc resolution.

### 5.2. Object với kiểu nguyên thủy

Mảnh code:

```java
public static Object triple(MethodHandles.Lookup lookup,
                            String name, Class<?> type, int base) {
    if (type != int.class) {
        throw new IllegalArgumentException("Expected int");
    }
    return Integer.valueOf(base * 3);
}
```

Hằng số `COUNT:I` có thể nhận giá trị `21` từ bootstrap ở dạng `Integer` nhờ chuyển đổi thích hợp của method handle/JVM. Khi bytecode thực hiện `ldc_w` cho entry này, JVM đẩy **một `int`**, không phải một tham chiếu tới `Integer`, lên operand stack. Điều này được xác minh bằng method `number()` trả `int` trong mục 8.

Nếu `CONSTANT_Dynamic` có descriptor `J` (`long`) hay `D` (`double`), việc nạp hai-slot constant dùng opcode `ldc2_w`, khác với `ldc`/`ldc_w` của hằng số một-slot như `int` hoặc reference.

### 5.3. Null hợp lệ khi type là reference

`java.lang.invoke.ConstantBootstraps.nullConstant` trong Java 11 có chữ ký:

```java
public static Object nullConstant(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type)
```

Nó có thể trả `null` cho một **reference type**. Ví dụ `EMPTY:Ljava/lang/String;` có thể resolve thành `null`; đây là giá trị hợp lệ cho `String`. Nhưng `null` **không** thể đại diện cho `int`, `boolean` hay một primitive khác; conversion tới primitive phải thất bại với `BootstrapMethodError`.

Đây là điểm khác với `invokedynamic`: bootstrap của call site phải trả một `CallSite` **không null** và có `MethodType` phù hợp, trong khi dynamic constant có thể hợp lệ với `null` nếu type là tham chiếu.

### 5.4. Trả sai kiểu: BootstrapMethodError

Nếu constant yêu cầu `String` nhưng bootstrap trả `Integer`:

```java
public static Object wrongType(MethodHandles.Lookup lookup,
                               String name, Class<?> type) {
    return Integer.valueOf(99);
}
```

Khi JVM thực hiện bước kiểm tra/chuyển đổi kết quả cho `WRONG:Ljava/lang/String;`, giá trị `Integer` không thể trở thành `String`. Theo **JVMS `5.4.3.6**, lỗi chuyển đổi kiểu (như `ClassCastException` hoặc `NullPointerException` khi unbox) làm resolution thất bại với **`BootstrapMethodError`**.

Nếu bootstrap tự ném một exception không thuộc `Error`, JVM thường bao bọc bằng `BootstrapMethodError` với cause tương ứng. Nếu chính bootstrap ném một `Error`, quy tắc lỗi khác: không mặc định mọi `Error` lại được bọc thêm.

**Đừng bắt `BootstrapMethodError` để tiếp tục chạy một đường xử lý bình thường với kết quả giả**, vì đây thường là lỗi liên kết, classfile hoặc cấu hình bootstrap. Cần sửa lỗi gốc, xác định tên entry, descriptor, method handle và các static arguments.

## 6. Thời điểm resolve, cache và concurrency

### 6.1. Không tương đương static initializer

`CONSTANT_Dynamic` là **symbolic reference trong runtime constant pool**. Nó được resolve khi JVM cần tham chiếu; JVM có quyền tiến hành các bước linking/resolution theo đặc tả, nên **không lấy thời điểm “lần đầu gọi phương thức” làm lịch tuyệt đối** trên mọi JVM.

Nó **khác** với `static { ... }` hoặc khởi tạo field `static final` thông thường qua `<clinit>`. Một class có thể được load, verify hay initialize mà không nhất thiết tất cả dynamic constants của nó đã được resolve. Việc quan sát thứ tự in log của bootstrap trong một lần chạy **không** được dùng làm hợp đồng về thứ tự khởi tạo ứng dụng.

Trong demo: sau khi `MethodHandles.lookup().defineClass(bytes)`, bộ đếm là `0/0`; gọi `message()` và `number()` làm chúng được resolve. Đây là **kết quả thực nghiệm của runtime đã kiểm thử**, không hứa mọi JVM đều trì hoãn chính xác đến cùng một điểm.

### 6.2. Kết quả resolution được cache theo symbolic reference

**JVMS `5.4.3** quy định: khi một symbolic reference tới dynamic constant resolve thành công, những lần dùng tiếp theo của **chính tham chiếu đó trong runtime constant pool** lấy lại cùng **giá trị đã resolve**; không giải quyết lại từ đầu.

Trong demo, gọi `message()` hai lần cho cùng entry dẫn đến `greeting` chạy **một lần** ở đường chạy tuần tự; gọi `number()` hai lần tương tự.

**Đừng đồng nhất “mỗi entry resolve một lần” với “bootstrap method chỉ có thể được gọi đúng một lần toàn chương trình”.** Có nhiều constant-pool entries khác nhau có thể dùng chung một bootstrap method; mỗi entry vẫn có resolution riêng. Class khác hoặc classloader khác có runtime constant pool khác. 

### 6.3. Nhiều thread có thể gọi bootstrap đồng thời

Điểm tinh tế trong **JVMS `5.4.3.6**: nếu nhiều thread cùng kích hoạt resolution của một dynamic constant, JVM **có thể gọi bootstrap method handle đồng thời nhiều lần** rồi chỉ **chọn một kết quả** để cài đặt; các kết quả khác bị bỏ qua.

Vì vậy bootstrap nên:

- Tránh side effect không an toàn hoặc có cơ chế concurrency control/idempotency thích hợp.
- Không lấy bộ đếm global không đồng bộ làm chứng cứ rằng bootstrap tuyệt đối chỉ chạy một lần.
- Nếu trả object mutable, xác định ownership, công bố an toàn và khả năng dùng chung reference.
- Tránh phụ thuộc vào thứ tự resolution giữa các entry khác nhau.
- Không dùng hành vi runtime nội bộ không được đặc tả làm cơ sở quản lý kết nối, transaction hay resource.

**Đây không phải memoization ứng dụng theo tên phương thức**. Cache thuộc **symbolic reference** của JVM, nên đặt static field trong bootstrap class hay gọi bootstrap trực tiếp sẽ có ý nghĩa khác.

### 6.4. Lỗi resolution cũng được ghi nhớ

Nếu một symbolic reference resolve thất bại, những lần thử dùng lại tham chiếu đó tiếp tục thất bại theo cơ chế JVM; JVM không tự “thử bootstrap lại cho đến khi thành công”. Đừng kỳ vọng thay đổi cấu hình runtime rồi gọi lại cùng `ldc` để tự khắc phục kết quả đã lỗi.

Trong demo, `invalid()` trả về `BootstrapMethodError` do kết quả sai kiểu. Ví dụ chỉ kiểm thử ca lỗi đầu; quy tắc cached failure được giải thích từ JVMS, không bị suy diễn từ một kết quả console đơn lẻ.

## 7. So sánh với constant truyền thống và invokedynamic

| Tính năng | Constant literal / `ConstantValue` | `CONSTANT_Dynamic` | `CONSTANT_InvokeDynamic` |
| --- | --- | --- | --- |
| Mục đích | Biểu diễn hằng số có sẵn ở dạng JVM hiểu trực tiếp | Tính ra **một giá trị** khi resolve | Tính ra **một call site** để gọi động |
| Constant pool tag | `String`/`Integer`/`Class`... tùy loại | **17** | **18** |
| Tên và type | Tùy dạng entry | **Field descriptor** | **Method descriptor** |
| Bootstrap | Không cần cho literal đơn giản | Có, trả giá trị chuyển được sang type | Có, trả `CallSite` đúng method type |
| Tham số thứ ba điển hình | Không có bootstrap | **`Class<?>`** | **`MethodType`** |
| Bytecode sử dụng | `ldc`, `getstatic`... tùy hằng | `ldc`/`ldc_w`/`ldc2_w` và ngữ cảnh loadable khác | **`invokedynamic`** |
| Kiểu giá trị cuối | Kiểu của constant/field | Primitive, reference; `null` hợp lệ cho reference | `CallSite` không null, method type tương ứng |
| Kết quả được ghi nhớ | Tùy cơ chế hằng truyền thống | Cache **resolution của symbolic reference** | Gắn kết **call site** theo quy tắc `invokedynamic` |

### 7.1. Java source constant variable không phải condy

Trong Java source:

```java
public static final int LIMIT = 10;
public static final String LABEL = "ready";
```

Các giá trị thuộc dạng **compile-time constant expression** có quy tắc riêng (JLS), và compiler có thể chèn literal vào bytecode ở nơi dùng. Không có nghĩa `javac` luôn tạo `CONSTANT_Dynamic` cho mọi `static final`. Một field `static final` có initializer runtime cũng **không tự trở thành condy** chỉ vì nó không phải compile-time constant.

**Không có cú pháp Java 11 source đơn giản kiểu `condy(...)` để khai báo `CONSTANT_Dynamic`**. Các trường hợp condy thực thường đến từ compiler, bytecode tool, language runtime hoặc classfile generator. Tại Java 11, có thể dùng thư viện như ASM phiên bản hỗ trợ tag 17 hoặc tạo classfile theo JVMS; bài này dùng một generator tối giản để không phải tải dependency.

### 7.2. Vì sao không dùng invokedynamic thay?

`invokedynamic` liên kết **việc gọi phương thức** qua `CallSite`, thích hợp với những call sites/dispatch có thể thay đổi mục tiêu. Condy giải quyết bài toán **lấy một giá trị**, ví dụ `MethodHandle`, `VarHandle`, `Class`, enum, object mô tả metadata hay primitive.

Cả hai dùng `BootstrapMethods`, nhưng **không được tráo kiểu kết quả**: condy `String` không trả `CallSite`; bootstrap của invokedynamic không nhận `Class<?>` chỉ vì có ba tham số đầu tương tự.

## 8. Chương trình Java 11 chạy thật: tạo CONSTANT_Dynamic và kiểm tra bootstrap

Ví dụ sau độc lập, **không dùng API nội bộ JDK**, không tải ASM hoặc thư viện ngoài. Nó xây một classfile version 55 tối giản bằng `DataOutputStream`, nạp class đó qua `MethodHandles.Lookup.defineClass`, rồi dùng reflection để gọi bốn method chứa `ldc_w` cho bốn dynamic constants.

**Các trường hợp được kiểm thử:**

1. `MESSAGE:Ljava/lang/String;` dùng bootstrap `greeting(Lookup, String, Class, String, int)`, với static args `"hello:"` và `7`. Kết quả là `String`.
2. `COUNT:I` dùng bootstrap `triple(Lookup, String, Class, int)`, nhận static arg `7` và trả `Integer(21)` để JVM chuyển thành `int`.
3. `EMPTY:Ljava/lang/String;` dùng `ConstantBootstraps.nullConstant` với **0 static args** và trả `null` hợp lệ.
4. `WRONG:Ljava/lang/String;` dùng bootstrap cố ý trả `Integer(99)`, bị JVM từ chối bằng `BootstrapMethodError`.
5. Gọi lại hai hằng số hợp lệ trong một thread và kiểm tra bootstrap **không bị gọi lại ở lần sử dụng tiếp theo**.

**Ghi chú về giới hạn:** generator viết đúng cấu trúc cần cho ví dụ (method static nhỏ, không có nhánh, constant pool đơn giản, classfile version 55). Nó **không phải thư viện sinh classfile production**: không tái sử dụng constant pool entry, không kiểm tra đầy đủ mọi giới hạn JVMS, không hỗ trợ hết opcode/attribute/kiểu. Khi cần tạo bytecode sản phẩm, hãy dùng công cụ được bảo trì và hỗ trợ Java version đích.

### 8.1. Mã hoàn chỉnh — CondyBootstrapDemo.java

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public class CondyBootstrapDemo {
    private static int textCalls;
    private static int numberCalls;
    private static int badCalls;

    public static String greeting(MethodHandles.Lookup lookup, String name,
                                  Class<?> type, String prefix, int number) {
        textCalls++;
        if (type != String.class) {
            throw new IllegalArgumentException("Expected String");
        }
        return prefix + name + "#" + number
                + "@" + lookup.lookupClass().getSimpleName();
    }

    public static Object triple(MethodHandles.Lookup lookup, String name,
                                Class<?> type, int base) {
        numberCalls++;
        if (type != int.class || !name.equals("COUNT")) {
            throw new IllegalArgumentException("Expected COUNT:int");
        }
        return Integer.valueOf(base * 3);
    }

    public static Object wrongType(MethodHandles.Lookup lookup, String name,
                                   Class<?> type) {
        badCalls++;
        return Integer.valueOf(99); // Sai kiểu cho constant String.
    }

    private static class Pool {
        final ByteArrayOutputStream data = new ByteArrayOutputStream();
        final DataOutputStream out = new DataOutputStream(data);
        int count = 1;

        int utf(String value) throws Exception {
            int index = count++;
            out.writeByte(1);
            out.writeUTF(value);
            return index;
        }

        int clazz(String internalName) throws Exception {
            int n = utf(internalName), index = count++;
            out.writeByte(7);
            out.writeShort(n);
            return index;
        }

        int nameType(String name, String descriptor) throws Exception {
            int n = utf(name), t = utf(descriptor), index = count++;
            out.writeByte(12);
            out.writeShort(n);
            out.writeShort(t);
            return index;
        }

        int string(String value) throws Exception {
            int u = utf(value), index = count++;
            out.writeByte(8);
            out.writeShort(u);
            return index;
        }

        int integer(int value) throws Exception {
            int index = count++;
            out.writeByte(3);
            out.writeInt(value);
            return index;
        }

        int methodRef(String owner, String name, String descriptor)
                throws Exception {
            int c = clazz(owner), n = nameType(name, descriptor);
            int index = count++;
            out.writeByte(10);
            out.writeShort(c);
            out.writeShort(n);
            return index;
        }

        int staticHandle(int methodRef) throws Exception {
            int index = count++;
            out.writeByte(15);
            out.writeByte(6); // REF_invokeStatic
            out.writeShort(methodRef);
            return index;
        }

        int dynamic(int bootstrapIndex, String name, String fieldDescriptor)
                throws Exception {
            int n = nameType(name, fieldDescriptor);
            int index = count++;
            out.writeByte(17); // CONSTANT_Dynamic
            out.writeShort(bootstrapIndex);
            out.writeShort(n);
            return index;
        }
    }

    private static void addMethod(DataOutputStream out, int nameIndex,
                                  int descriptorIndex, int codeIndex,
                                  int dynamicIndex, int returnOpcode)
            throws Exception {
        byte[] code = new byte[] {
            0x13, (byte) (dynamicIndex >>> 8),
            (byte) dynamicIndex, (byte) returnOpcode
        }; // ldc_w <constant-pool-index>; areturn / ireturn

        out.writeShort(0x0009);  // public static
        out.writeShort(nameIndex);
        out.writeShort(descriptorIndex);
        out.writeShort(1);       // Một Code attribute
        out.writeShort(codeIndex);
        out.writeInt(12 + code.length);
        out.writeShort(1);       // max_stack
        out.writeShort(0);       // max_locals
        out.writeInt(code.length);
        out.write(code);
        out.writeShort(0);       // exception_table_length
        out.writeShort(0);       // Code attributes
    }

    private static byte[] generate() throws Exception {
        Pool cp = new Pool();
        int self = cp.clazz("CondyGenerated");
        int object = cp.clazz("java/lang/Object");
        int codeAttribute = cp.utf("Code");
        int bootstrapAttribute = cp.utf("BootstrapMethods");

        String head = "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/Class;";

        int greetingHandle = cp.staticHandle(cp.methodRef(
                "CondyBootstrapDemo", "greeting",
                head + "Ljava/lang/String;I)Ljava/lang/String;"));
        int numberHandle = cp.staticHandle(cp.methodRef(
                "CondyBootstrapDemo", "triple",
                head + "I)Ljava/lang/Object;"));
        int badHandle = cp.staticHandle(cp.methodRef(
                "CondyBootstrapDemo", "wrongType",
                head + ")Ljava/lang/Object;"));
        int nullHandle = cp.staticHandle(cp.methodRef(
                "java/lang/invoke/ConstantBootstraps", "nullConstant",
                head + ")Ljava/lang/Object;"));

        int prefix = cp.string("hello:");
        int seven = cp.integer(7);

        int message = cp.dynamic(0, "MESSAGE", "Ljava/lang/String;");
        int count = cp.dynamic(1, "COUNT", "I");
        int invalid = cp.dynamic(2, "WRONG", "Ljava/lang/String;");
        int nullable = cp.dynamic(3, "EMPTY", "Ljava/lang/String;");

        int nameMessage = cp.utf("message");
        int refString = cp.utf("()Ljava/lang/String;");
        int nameNumber = cp.utf("number");
        int refInt = cp.utf("()I");
        int nameInvalid = cp.utf("invalid");
        int nameNullable = cp.utf("nullable");

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        out.writeInt(0xCAFEBABE);
        out.writeShort(0);       // minor version
        out.writeShort(55);      // Java 11 classfile
        out.writeShort(cp.count);
        out.write(cp.data.toByteArray());
        out.writeShort(0x0021);  // ACC_PUBLIC | ACC_SUPER
        out.writeShort(self);
        out.writeShort(object);
        out.writeShort(0);       // interfaces
        out.writeShort(0);       // fields
        out.writeShort(4);       // methods

        addMethod(out, nameMessage, refString,
                codeAttribute, message, 0xB0);
        addMethod(out, nameNumber, refInt,
                codeAttribute, count, 0xAC);
        addMethod(out, nameInvalid, refString,
                codeAttribute, invalid, 0xB0);
        addMethod(out, nameNullable, refString,
                codeAttribute, nullable, 0xB0);

        out.writeShort(1);       // Một class-level attribute
        out.writeShort(bootstrapAttribute);
        out.writeInt(24);        // 2 + (8 + 6 + 4 + 4)
        out.writeShort(4);       // Bốn bootstrap entries

        out.writeShort(greetingHandle);
        out.writeShort(2);
        out.writeShort(prefix);
        out.writeShort(seven);

        out.writeShort(numberHandle);
        out.writeShort(1);
        out.writeShort(seven);

        out.writeShort(badHandle);
        out.writeShort(0);

        out.writeShort(nullHandle);
        out.writeShort(0);
        out.flush();
        return buffer.toByteArray();
    }

    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        byte[] code = generate();

        // Ghi classfile ra thư mục hiện hành để dùng javap.
        Files.write(Path.of("CondyGenerated.class"), code);
        Class<?> generated =
                MethodHandles.lookup().defineClass(code);

        check(textCalls == 0 && numberCalls == 0,
                "Bootstrap called too soon");
        System.out.println("before resolution = "
                + textCalls + "/" + numberCalls);

        Method message = generated.getMethod("message");
        String first = (String) message.invoke(null);
        String second = (String) message.invoke(null);
        check(Objects.equals(first,
                        "hello:MESSAGE#7@CondyGenerated")
                        && first == second
                        && textCalls == 1,
                "Text constant not cached");
        System.out.println("text result = " + first);
        System.out.println("text bootstrap calls = " + textCalls);

        Method number = generated.getMethod("number");
        int n1 = (Integer) number.invoke(null);
        int n2 = (Integer) number.invoke(null);
        check(n1 == 21 && n2 == 21 && numberCalls == 1,
                "Primitive constant not resolved");
        System.out.println("int result = " + n1);
        System.out.println("int bootstrap calls = " + numberCalls);

        check(generated.getMethod("nullable").invoke(null) == null,
                "Reference-typed constant may be null");
        System.out.println("null reference = true");

        Method bad = generated.getMethod("invalid");
        boolean rejected = false;
        try {
            bad.invoke(null);
        } catch (InvocationTargetException error) {
            rejected = error.getCause()
                    instanceof BootstrapMethodError;
        }
        check(rejected && badCalls == 1,
                "Wrong return type not rejected");
        System.out.println("wrong type rejected = true");
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Chương trình này **không tạo constructor `CondyGenerated`** vì bốn method được định nghĩa đều là `public static`, và không cần tạo instance. `MethodHandles.Lookup.defineClass(bytes)` có trong Java 11; class sinh ra cùng package và class loader thích hợp với lookup. Demo dùng default package để tránh cấu hình package, **không** khuyến nghị dùng default package cho code production.

**Lệnh biên dịch và chạy:**

```bash
javac --release 11 CondyBootstrapDemo.java
java CondyBootstrapDemo
```

**Đầu ra đã kiểm chứng với classfile Java 11:**

```text
before resolution = 0/0
text result = hello:MESSAGE#7@CondyGenerated
text bootstrap calls = 1
int result = 21
int bootstrap calls = 1
null reference = true
wrong type rejected = true
ALL CHECKS PASSED
```

**Lưu ý:** class `CondyBootstrapDemo` có nguồn Java và được biên dịch bằng `javac --release 11`; class `CondyGenerated` là **bytecode được tạo động** và ghi ra file `CondyGenerated.class` trong **thư mục chạy** để kiểm tra. Demo dùng runtime Java 11 trở lên và không cần thư viện ngoài. Xóa file `CondyGenerated.class` sau khi kiểm tra nếu không cần giữ. Mã tạo class có tên cố định: chạy mỗi lượt trong một JVM mới, không cố gọi `defineClass` hai lần với cùng tên trong một loader.

### 8.2. Kiểm chứng bằng javap

Chạy sau lệnh `java`:

```bash
javap -v -p CondyGenerated
```

Trong kết quả đã kiểm chứng, `javap` hiển thị:

```text
major version: 55
...
#41 = Dynamic            #0:#40         // #0:MESSAGE:Ljava/lang/String;
#45 = Dynamic            #1:#44         // #1:COUNT:I
#49 = Dynamic            #2:#48         // #2:WRONG:Ljava/lang/String;
#53 = Dynamic            #3:#52         // #3:EMPTY:Ljava/lang/String;
...
0: ldc_w         #41                 // Dynamic #0:MESSAGE:Ljava/lang/String;
...
0: ldc_w         #45                 // Dynamic #1:COUNT:I
...
BootstrapMethods:
  ...
```

Các **constant pool indexes cụ thể** như `#41`, `#45` có thể thay đổi nếu sửa generator hoặc tool; **không** coi chúng là API ổn định. Điều cần nhìn là:

- `major version: 55` → classfile tương thích Java 11.
- `Dynamic` → constant pool tag **17** thật, không phải chuỗi tên giả.
- `#0:MESSAGE:Ljava/lang/String;` và `#1:COUNT:I` → bootstrap index, tên và **field descriptor**.
- `ldc_w` → bytecode load dynamic constant. Với descriptor `I`, `ireturn` lấy kết quả primitive.
- `BootstrapMethods:` → bảng method handle và static arguments được JVM sử dụng khi resolve.

### 8.3. Vì sao ví dụ kiểm tra cả sai kiểu?

Nếu chỉ tạo một bootstrap rồi **gọi trực tiếp `greeting(...)` trong `main`**, chương trình sẽ kiểm tra logic nối chuỗi nhưng **không chứng minh cơ chế `CONSTANT_Dynamic` hoạt động**.

Ở đây, classfile có entry `CONSTANT_Dynamic`, bytecode `ldc_w`, attribute `BootstrapMethods`, BSM method handles và các static arguments thật. Khi `invalid()` nạp `WRONG:Ljava/lang/String;`, **JVM** tự kiểm tra kiểu và ném `BootstrapMethodError`; ứng dụng không tự viết câu lệnh `throw new BootstrapMethodError(...)`. Điều này làm rõ **đây là contract của JVM**, không phải một convention của hàm Java.

## 9. ConstantBootstraps có sẵn trong JDK 11

Java 11 cung cấp `java.lang.invoke.ConstantBootstraps` — tập phương thức bootstrap tiêu chuẩn để compiler/tool có thể dùng khi mô tả condy:

| Phương thức | Vai trò |
| --- | --- |
| `nullConstant(Lookup, String, Class<?>)` | Tạo `null` cho constant thuộc reference type |
| `primitiveClass(Lookup, String, Class<?>)` | Tạo `Class` mirror cho primitive type theo descriptor |
| `enumConstant(Lookup, String, Class<E>)` | Lấy enum constant theo tên và kiểu enum |
| `getStaticFinal(...)` | Lấy giá trị static final field theo quy tắc thích hợp |
| `invoke(...)` | Invoke method handle với tham số chỉ định để tạo kết quả |
| `fieldVarHandle(...)` | Tạo `VarHandle` cho instance field |
| `staticFieldVarHandle(...)` | Tạo `VarHandle` cho static field |
| `arrayVarHandle(...)` | Tạo `VarHandle` cho array element |

**Không tự suy diễn rằng mọi phiên bản của `ConstantBootstraps` có cùng tập phương thức**: khi dùng Java 11, tra đúng Javadoc **Java 11**. Ví dụ `explicitCast` xuất hiện ở API JDK mới hơn; không viết code gọi nó rồi tuyên bố biên dịch với `--release 11`.

Với `nullConstant`, ví dụ classfile ở mục 8 thật sự dùng `CONSTANT_MethodHandle` trỏ tới phương thức của JDK; không cần tạo bootstrap tự viết cho trường hợp `null`.

### 9.1. Vì sao không nên tự viết bootstrap cho mọi việc?

Bootstrap method tùy biến hữu ích khi kết quả cần tính theo metadata, lookup context hoặc phối hợp logic phức tạp. Tuy nhiên, nếu yêu cầu chỉ là `null`, enum, primitive class mirror, `VarHandle` hoặc truy cập một static final field, các bootstrap tiêu chuẩn thường **ít code và ít sai sót** hơn.

Dùng BSM custom cần quan tâm tới:

- Quyền truy cập của method handle và lookup.
- Kiểu và số lượng static arguments.
- Chi phí resolution lần đầu.
- Khả năng lặp invocation khi nhiều thread resolve cùng tham chiếu.
- Kết quả mutable được cache và chia sẻ.
- Xử lý lỗi type mismatch và exception.

Không dùng BSM như một constructor toàn cục tùy tiện mở file/network/transaction mỗi khi class được load; timing resolution và concurrency không phù hợp cho nhiều tác vụ lifecycle của ứng dụng.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `BootstrapMethodError` ngay khi `ldc` chạy | Bootstrap trả sai kiểu, thiếu quyền hoặc sai chữ ký/cấu hình | Kiểm tra cause, descriptor, method handle, static args và quyền truy cập |
| Tham số thứ ba không đúng kỳ vọng | Nhầm `Class<?>` của condy với `MethodType` của invokedynamic | Với `CONSTANT_Dynamic`, dùng `Class<?> type` |
| `MethodType` được truyền thay vì `Class<?>` | Dùng mô hình bootstrap cho call site | Phân biệt tag 17 và 18, field descriptor với method descriptor |
| `ClassCastException`/`BootstrapMethodError` ở kiểu kết quả | Giá trị không chuyển được tới descriptor | Trả đúng reference/primitive wrapper tương ứng |
| `null` dùng cho constant `int` | Primitive không nhận null | Chọn giá trị số thích hợp; null chỉ dùng với reference |
| `NoSuchMethodError` hoặc lỗi MethodHandle | Bootstrap method owner/name/descriptor không khớp | Dùng method descriptor chính xác, validate classfile |
| `IllegalAccessError` | JVM không cho bootstrap handle tham chiếu method cần thiết | Kiểm tra visibility/module/nest và `Lookup` đúng context |
| JVM từ chối classfile | Không có `BootstrapMethods`, sai index/tag/field descriptor/attribute length | Đọc JVMS `4.4.10/`4.7.23, kiểm tra `javap -v` |
| Bootstrap chạy khác số lần mong đợi | Có nhiều CP entries, nhiều loaders hoặc concurrency | Cache theo symbolic reference, bootstrap side effects phải an toàn |
| Constant không được resolve khi mong đợi | Resolution timing không phải scheduler của ứng dụng | Không dựa vào thời điểm BSM để chạy startup task |
| Dùng cùng bootstrap nhưng không cùng giá trị | Name/type/static args khác nhau hoặc classloader khác | Phân biệt tham chiếu runtime constant pool |
| Chu trình giữa các dynamic arguments | INNER lại phụ thuộc OUTER | Tránh dependency cycle; JVMS có thể báo `StackOverflowError` |
| Demo gọi bootstrap trực tiếp nhưng không thấy Dynamic entry | Không tạo `CONSTANT_Dynamic` trong classfile | Dùng bytecode tool/classfile generator và xem bằng `javap -v` |
| Dùng `ldc_w` cho `long`/`double` dynamic constant | Sai opcode cho kiểu hai slot | Dùng `ldc2_w` với `J`/`D` |
| Dùng classfile major 52 mà chứa tag 17 | Version không hỗ trợ condy | Chọn classfile major 55+ theo Java 11 |
| Compile-time `static final` bị hiểu nhầm là condy | ConstantValue, `<clinit>` và condy là cơ chế khác nhau | Kiểm tra classfile thực bằng `javap -v` |

**Khi có lỗi, đọc cả nguyên nhân sâu hơn:** `BootstrapMethodError.getCause()`, stack trace và exception gốc từ BSM thường chỉ ra sai số tham số, lỗi lookup hoặc kết quả không phù hợp. Không bao giờ nuốt `LinkageError`/`BootstrapMethodError` rồi chạy nghiệp vụ với một giá trị “mặc định an toàn” tự đặt mà không đánh giá hậu quả.

## 11. Checklist viết hoặc kiểm tra một bootstrap method

1. **Xác định đúng loại entry:** `CONSTANT_Dynamic` (tag 17), không phải `CONSTANT_InvokeDynamic` (tag 18).
2. **Tên và descriptor:** `CONSTANT_NameAndType` có **field descriptor** hợp lệ, không phải method descriptor.
3. **BSM handle:** trỏ tới method/constructor có thể được JVM resolve, với access quyền phù hợp.
4. **Đối số đầu:** `MethodHandles.Lookup` cho caller class, `String name`, `Class<?> type`. Kiểm tra đúng type được truyền.
5. **Static args:** chỉ gồm loadable constants, truyền theo đúng thứ tự; có thể gồm condy phụ thuộc.
6. **Chuyển đổi dữ liệu:** xử lý `int`, `long`, `boolean`, kiểu tham chiếu, `null` theo descriptor; không trả sai class.
7. **Không tạo cycle:** hằng số phụ thuộc nhau không được tạo chu trình tự tham chiếu.
8. **Không lạm dụng side effect:** resolution có cache, nhưng bootstrap có thể chạy cạnh tranh khi nhiều thread.
9. **Security:** không dùng `Lookup` để vượt access control hoặc chia sẻ secret tùy tiện dưới dạng constant được cache.
10. **Chẩn đoán:** dùng `javap -v -p` để xem `Dynamic`, `MethodHandle` và `BootstrapMethods`.
11. **Tương thích Java 11:** classfile major 55 và API thực sự có từ Java 11; không trộn API `java.lang.classfile` JDK mới vào lệnh `--release 11`.
12. **Kiểm thử thực:** chạy `ldc` thật, kiểm tra kết quả, lỗi sai kiểu và hành vi resolution trong tình huống cần thiết.

## 12. Bài tập tự kiểm tra

**Câu 1.** Trong `CONSTANT_Dynamic_info`, `bootstrap_method_attr_index` dùng để làm gì?  
**Đáp án:** Nó chọn một entry trong class-level `BootstrapMethods.bootstrap_methods[]`, từ đó JVM tìm method handle và các static args.

**Câu 2.** Vì sao `COUNT:I` khác với `MESSAGE:Ljava/lang/String;`?  
**Đáp án:** `I` là field descriptor của `int`, còn `Ljava/lang/String;` là của reference type `String`. `type` mà BSM nhận lần lượt là `int.class` và `String.class`, và giá trị trả về phải chuyển được sang kiểu đó.

**Câu 3.** Ba tham số đầu convention của condy bootstrap là gì?  
**Đáp án:** `MethodHandles.Lookup lookup`, `String name` và `Class<?> type`. Các static arguments đứng sau theo đúng thứ tự classfile.

**Câu 4.** Tại sao static arg `7` có thể truyền vào BSM nhận `int base`?  
**Đáp án:** JVM resolve hằng số số và lời gọi method handle thực hiện các chuyển đổi thích hợp, bao gồm boxing/unboxing khi cần.

**Câu 5.** `String nullConstant(...)` có phải cách khai báo JDK 11 không?  
**Đáp án:** Không. `ConstantBootstraps.nullConstant` trả `Object`, có thể là `null`; JVM kiểm tra với reference type của dynamic constant.

**Câu 6.** Nếu BSM trả `Integer` cho hằng số có descriptor `Ljava/lang/String;` thì sao?  
**Đáp án:** Không thể chuyển về `String`, resolution thất bại với `BootstrapMethodError`.

**Câu 7.** Một bootstrap có `textCalls` tăng một lần khi gọi `ldc` hai lần, vậy nó luôn chạy đúng một lần trong mọi môi trường?  
**Đáp án:** Không. Với nhiều thread resolve đồng thời, BSM có thể được invoke nhiều lần, nhưng JVM chọn và cache một kết quả cho symbolic reference. Có nhiều entry/classloader cũng tạo resolution riêng.

**Câu 8.** Condy có thể nhận một `CONSTANT_Dynamic` khác làm static argument không?  
**Đáp án:** Có. JVM resolve dynamic constant phụ thuộc trước. Nhưng cycle giữa các dynamic constants không được hỗ trợ.

**Câu 9.** `CONSTANT_Dynamic` có phải tên khác của `invokedynamic`?  
**Đáp án:** Không. Condy tạo một **giá trị** với field descriptor; `invokedynamic` tạo **CallSite** với method descriptor.

**Câu 10.** Vì sao code có `static final String NAME = "X";` chưa chắc là condy?  
**Đáp án:** Đây thường là Java compile-time constant, không cần BSM. Muốn xác nhận có condy, phải xem classfile có `CONSTANT_Dynamic` (tag 17) và `BootstrapMethods` không.

## 13. Tổng kết

```text
CONSTANT_Dynamic (tag 17)
  ├─ bootstrap index -> BootstrapMethods entry
  │     ├─ MethodHandle (BSM)
  │     └─ Static args (String/int/Class/MethodHandle/condy...)
  └─ NameAndType
        ├─ name  : MESSAGE
        └─ field descriptor : Ljava/lang/String;
                  |
                  v
  BSM(lookup, "MESSAGE", String.class, ...staticArgs)
                  |
                  v
        kết quả BSM -> JVM kiểm tra/chuyển kiểu
                  |
                  v
        cache resolution / lỗi theo symbolic reference
                  |
                  v
        ldc, ldc_w (hoặc ldc2_w cho J/D)
```

**Ba ý cần nhớ:**

- **Bootstrap method** là code tính giá trị hằng số trong lúc JVM resolve; đối số đầu dùng `Lookup` của class tham chiếu, theo sau là **tên**, **kiểu đích** và **static args**.
- **Static arguments** là những **loadable constants được chỉ định trong `BootstrapMethods`**, được resolve và truyền theo thứ tự; chúng không tự biến thành field của class Java.
- **Kiểu kết quả** được quyết định bởi **field descriptor của `CONSTANT_Dynamic`**, không phải chỉ bởi kiểu return khai báo trong BSM. Kết quả sai kiểu làm resolution thất bại; kết quả hợp lệ được ghi nhớ cho tham chiếu đó.

Với Java 11+, `CONSTANT_Dynamic` vẫn là cơ chế classfile hữu ích cho compiler/language runtime/tooling. Người viết ứng dụng Java thông thường **không cần tự tạo condy** nếu không xây bytecode, nhưng việc hiểu BSM và kiểu kết quả giúp đọc stack trace, phân tích `javap` và chẩn đoán lỗi liên kết chính xác.

### Tài liệu tham khảo chính thức còn áp dụng

- [OpenJDK JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309)
- [Java SE 11 — JVMS `4.4.10: CONSTANT_Dynamic_info và CONSTANT_InvokeDynamic_info](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10)
- [Java SE 11 — JVMS `4.7.23: BootstrapMethods attribute](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.23)
- [Java SE 11 — JVMS `5.4.3.6: Dynamically-Computed Constant and Call Site Resolution](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6)
- [Java SE 11 — java.lang.invoke.ConstantBootstraps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html)
- [Java SE 11 — java.lang.invoke.MethodHandles.Lookup.defineClass](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 11 — java.lang.invoke package summary: bootstrap method invocation](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/package-summary.html)
- [Java SE 25 — JVMS `5.4.3.6: cơ chế dynamic constant vẫn được đặc tả](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4.3.6)
