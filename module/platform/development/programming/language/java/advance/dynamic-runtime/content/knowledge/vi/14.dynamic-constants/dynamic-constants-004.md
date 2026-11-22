# 14.4. ConstantBootstraps cho null, enum, static final và VarHandle

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu **hằng động** (*dynamic constant*, thường gọi là **condy**) trong JVM, mục đích của `CONSTANT_Dynamic_info` và vai trò của **bootstrap method** khi liên kết một hằng.
2. Phân biệt **kết quả hằng động** với **hàm bootstrap dùng để tính kết quả**; hiểu vì sao gọi một phương thức `ConstantBootstraps` thông thường **không** tự tạo một constant-pool entry.
3. Dùng chính xác `java.lang.invoke.ConstantBootstraps.nullConstant` để biểu diễn hằng `null` có **kiểu tham chiếu**, và nhận biết lỗi khi dùng primitive type.
4. Dùng `enumConstant` để lấy đúng phần tử enum từ tên hằng và `Class<E>`.
5. Dùng hai overload của `getStaticFinal` để đọc giá trị một trường `static final`, phân biệt **kiểu field**, **class khai báo field** và trường hợp overload ngắn có thể suy ra class khai báo.
6. Dùng `fieldVarHandle`, `staticFieldVarHandle` và `arrayVarHandle` để liên kết một `VarHandle` mô tả field instance, field static hoặc phần tử array.
7. Liên hệ các bootstrap trên với `java.lang.constant.ConstantDescs`, `DynamicConstantDesc` và `resolveConstantDesc` (cách mô phỏng resolution bằng Java code), không nhầm nó với `ldc` thực tế.
8. Xử lý lỗi type mismatch, access, thiếu field/enum, tính bất biến của kết quả hằng động và tính **biến đổi được của biến được một VarHandle trỏ tới**.

**Ngữ cảnh:** Trong chương **14. Hằng động** của Java Advance – dynamic-runtime, Java 11 đã bổ sung khả năng để một entry trong constant pool nhận giá trị do **bootstrap method** tính ra khi được resolve. JDK cung cấp sẵn `ConstantBootstraps` để không phải tự viết bootstrap cho những tình huống phổ biến: `null` có kiểu, enum constant, `static final` field, và `VarHandle`.

## 1. Hằng động trong JVM là gì?

Ở cấp class file, `CONSTANT_Dynamic_info` ghi lại một **tham chiếu biểu tượng** tới một hằng có giá trị sẽ được tính trong quá trình **resolution**, thay vì lưu trọn giá trị đó dưới dạng một literal thông thường trong class file.

Một bản mô tả hằng động về cơ bản cần:

- **Tên hằng** (*name*): chuỗi tên truyền cho bootstrap, có thể mang ý nghĩa nghiệp vụ (tên enum, tên field) hoặc không được dùng.
- **Kiểu hằng** (*type*): field descriptor ở cấp JVM, khi bootstrap chạy được chuyển thành đối tượng `Class<?>`.
- **Bootstrap method handle**: chỉ tới hàm được JVM gọi để tính giá trị.
- **Static bootstrap arguments**: dữ liệu bổ sung, nếu bootstrap cần (ví dụ `Class` của nơi khai báo field và `Class` của kiểu field).
- **Lookup context**: JVM cung cấp `MethodHandles.Lookup` phản ánh ngữ cảnh resolution và quyền truy cập của class sở hữu tham chiếu.

Hình dung:

```text
Class file:
  CONSTANT_Dynamic_info {
      name: "FAST"
      type: Lcom/example/Mode;
      bootstrap: ConstantBootstraps.enumConstant
      staticArgs: []
  }

Khi symbol được resolve:
  JVM tạo Lookup + name + type + staticArgs
      -> gọi bootstrap method
      -> kiểm tra kết quả phù hợp kiểu hằng
      -> công bố giá trị đã resolve cho các lần dùng sau
```

Ví dụ dạng trên chỉ là **sơ đồ** chứ không phải cú pháp Java hay bản dump chính xác của một class file. Trong bytecode thật, entry còn liên hệ `BootstrapMethods` attribute và các index trong constant pool. `ldc`, `ldc_w` hoặc `ldc2_w` có thể yêu cầu resolution của một dynamic constant.

### 1.1. `CONSTANT_Dynamic_info` khác `CONSTANT_InvokeDynamic_info`

| Khía cạnh | Dynamic constant (`condy`) | Dynamic call site (`invokedynamic`) |
| --- | --- | --- |
| Dữ liệu được bootstrap tạo | **Giá trị hằng** phù hợp field type | **`CallSite`** có `MethodType` phù hợp |
| Kiểu mô tả trong entry | **Field descriptor** như `Ljava/lang/String;`, `I`, `Ljava/lang/invoke/VarHandle;` | **Method descriptor** như `(Ljava/lang/Object;)Ljava/lang/String;` |
| Tình huống tiêu biểu | Hằng `null`, enum, `static final` field, handle truy cập biến | Liên kết lời gọi động |
| Sử dụng trong bytecode | Thường từ `ldc` hoặc làm bootstrap argument | Từ `invokedynamic` |
| Bootstrap có phải trả `CallSite`? | **Không**; trả giá trị của hằng | **Có** |

Đừng nhầm `ConstantBootstraps.` với `LambdaMetafactory` hoặc bootstrap trả `CallSite`: `ConstantBootstraps` tập trung vào **hằng động**, không tạo một lời gọi mới mặc định.

### 1.2. Khi nào bootstrap chạy? Có được cache không?

Khi một symbolic reference tới dynamic constant **được resolve thành công**, các lần resolve tiếp theo của **chính reference đó trong run-time constant pool** sử dụng cùng giá trị, không gọi lại bootstrap. Nếu resolution thất bại, JVM lưu lại kết quả thất bại theo quy tắc lỗi resolution.

Nhưng cần ghi nhớ hai giới hạn:

1. **Có thể có bootstrap invocations đồng thời.** Nếu nhiều thread cùng cố resolve một reference chưa liên kết, JVM có thể chạy bootstrap đồng thời hơn một lần, sau đó chọn một kết quả để công bố; không viết bootstrap có side effect rồi giả định nó chắc chắn chỉ chạy đúng một lần trong mọi interleaving.
2. **Cache của JVM áp dụng cho resolution của symbol trong constant pool, không phải mọi lệnh gọi Java thông thường.** Nếu code tự gọi `ConstantBootstraps.getStaticFinal(...)` hai lần, đó là hai lời gọi method bình thường. Nếu code gọi `DynamicConstantDesc.resolveConstantDesc(...)` hai lần, API này **không cache** kết quả resolution mô phỏng.

Cũng đừng hiểu "hằng đã resolve" là mọi object mà hằng trỏ đến đều bất biến. Một hằng có thể là tham chiếu tới một `VarHandle` hoặc một object mutable; **reference** có thể cố định trong pool, trong khi **trạng thái đối tượng/biến đích** vẫn thay đổi.

## 2. Signature chung của các bootstrap chuẩn

`ConstantBootstraps` là lớp `final` chứa các **phương thức static**. Nhìn chung, ba tham số đầu của bootstrap cho dynamic constant có ý nghĩa:

```text
(MethodHandles.Lookup lookup, String name, Class<?> type, ...staticArgs)
```

Trong đó:
- `lookup`: ngữ cảnh class thực hiện linkage, dùng khi bootstrap cần kiểm tra quyền.
- `name`: tên của constant-pool entry; ví dụ tên enum/field.
- `type`: **kiểu giá trị constant cần tạo**, *không phải* kiểu của class chứa bootstrap.
- `...staticArgs`: dữ liệu tùy phương thức, ví dụ `declaringClass`, `fieldType`, `arrayClass`.

Các bootstrap khác nhau **không dùng mọi tham số**. `nullConstant` không dùng `lookup`/`name`; `arrayVarHandle` không dùng `name`, trong khi `enumConstant` và `getStaticFinal` cần tên có ý nghĩa.

### 2.1. Bảng API chính của bài

| Bootstrap | Ý nghĩa | Thông tin quyết định kết quả |
| --- | --- | --- |
| `nullConstant(lookup, name, type)` | Hằng `null` thuộc một **reference type** | `type` là reference type |
| `enumConstant(lookup, name, type)` | Lấy enum constant | `name` chính xác và `type` là enum class |
| `getStaticFinal(lookup, name, type, declaringClass)` | Giá trị của trường `static final` | Tên, kiểu field, class khai báo và quyền truy cập |
| `getStaticFinal(lookup, name, type)` | Biến thể ngắn | Suy class khai báo từ `type`, hoặc wrapper class nếu field primitive |
| `fieldVarHandle(lookup, name, VarHandle.class, declaringClass, fieldType)` | Handle tới instance field | Tên field, owner, field type và quyền |
| `staticFieldVarHandle(lookup, name, VarHandle.class, declaringClass, fieldType)` | Handle tới static field | Tên field, owner, field type và quyền |
| `arrayVarHandle(lookup, name, VarHandle.class, arrayClass)` | Handle tới phần tử mảng | `arrayClass`, component type và quyền |

`ConstantBootstraps` còn có `primitiveClass`, `explicitCast`, `invoke`; đó là các bootstrap bổ trợ khác, không phải trọng tâm của bài này.

## 3. `nullConstant` — hằng null có kiểu

Signature:

```java
public static Object nullConstant(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type)
```

Đây là **chữ ký minh họa** của API đã tồn tại trong JDK, không phải code cần tự khai báo.

Hàm trả `null` nếu `type` là **reference type**, ví dụ:
- `String.class`;
- `Object.class`;
- `Integer.class`;
- `int[].class` (mảng cũng là reference type).

Ví dụ sử dụng trực tiếp:

```java
Object result = ConstantBootstraps.nullConstant(
        MethodHandles.lookup(), "unused", String.class);
System.out.println(result == null); // true
```

Đây là ví dụ nhỏ đặt trong method có import `ConstantBootstraps` và `MethodHandles`. Kết quả là **giá trị null**, chứ không phải object `String` mới được tạo. Khi một hằng dynamic có field descriptor `Ljava/lang/String;`, bootstrap null có thể cung cấp đúng giá trị hằng cho reference type ấy.

### 3.1. Vì sao primitive type không hợp lệ?

`null` không thể đại diện cho `int`, `long`, `boolean` hay `void`. Vì vậy:

```java
ConstantBootstraps.nullConstant(
        MethodHandles.lookup(), "unused", int.class);
```

Lời gọi này ném **`IllegalArgumentException`**, không phải trả `0` hoặc một giá trị boxed `Integer`. Với `void.class` cũng không tạo một null constant hợp lệ.

Không nhầm với `Void.class`: đó là một **reference class** nên `nullConstant(..., Void.class)` có thể trả `null`, nhưng `void.class` không phải reference type.

### 3.2. Khi nào có ích?

Một ngôn ngữ nguồn chạy trên JVM có thể cần một hằng mang **kiểu tham chiếu cụ thể** trong constant pool mà giá trị của nó là `null`. Bootstrap `nullConstant` cung cấp cách chuẩn hóa việc này ở cấp JVM. Trong Java code thông thường, bạn không cần `ConstantBootstraps` chỉ để gán `String s = null;`; giá trị học tập nằm ở **cơ chế liên kết hằng động**.

## 4. `enumConstant` — liên kết một phần tử enum theo tên

Signature tổng quát:

```java
public static <E extends Enum<E>> E enumConstant(
        MethodHandles.Lookup lookup, String name, Class<E> type)
```

Ở đây:
- `name` phải đúng **tên enum constant**, phân biệt chữ hoa/chữ thường;
- `type` phải là `Class<E>` của **một enum thực sự**, không phải `Enum.class` chung hoặc tên class ở dạng chuỗi;
- `lookup` xác định quyền truy cập trong quá trình liên kết.

Ví dụ:

```java
enum Mode { FAST, SLOW }

Mode mode = ConstantBootstraps.enumConstant(
        MethodHandles.lookup(), "FAST", Mode.class);
System.out.println(mode); // FAST
```

Đây là **đoạn minh họa không độc lập**; phần khai báo `enum` cần đặt đúng ngữ cảnh Java, ví dụ trong class ở phần chương trình hoàn chỉnh. Kết quả là **chính enum singleton `Mode.FAST`**, không phải instance `new Mode(...)`.

### 4.1. Những lỗi điển hình

| Đầu vào | Kết quả |
| --- | --- |
| `name = "FAST"`, `type = Mode.class` | Trả `Mode.FAST` |
| `name = "fast"` | `IllegalArgumentException` nếu enum không có constant tên chính xác đó |
| `name = "MISSING"` | `IllegalArgumentException` |
| `type` không phải enum class | `IllegalArgumentException` (với cách gọi có thể vượt qua kiểm tra generic compile-time) |
| Enum hoặc field không thể truy cập bằng lookup | Có thể ném `IllegalAccessError` |

Về mặt ý nghĩa, nó có quan hệ với `Enum.valueOf(type, name)`, nhưng **không nên thay thế máy móc** bởi lời gọi `valueOf`: bootstrap dùng đúng ngữ cảnh access và hợp đồng linkage của JVM.

### 4.2. Vì sao tên hằng quan trọng?

`enumConstant` đọc **name của dynamic constant** để quyết định enum constant nào sẽ được chọn. Nếu một generator bytecode đặt name sai, bootstrap **không tự đoán** alias hoặc chuyển sang enum constant mặc định. Khi làm DSL/runtime compiler, nên xác thực danh mục enum name trước khi phát sinh bytecode, đồng thời vẫn xử lý linkage failure nếu enum library thay đổi sau khi build.

## 5. `getStaticFinal` — lấy giá trị của một field static final

Có **hai overload**:

```java
Object getStaticFinal(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        Class<?> declaringClass);

Object getStaticFinal(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type);
```

Các chữ ký trên được viết để **tham khảo**, không cần tự triển khai.

### 5.1. Overload bốn tham số: khai báo rõ owner

Ví dụ class:

```java
static final class Settings {
    static final String LABEL = "ready";
    static final int LIMIT = 17;
}
```

Đây là class nested minh họa. `Settings` cần thuộc đúng nơi mà `lookup` có quyền truy cập.

Dùng:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();

Object label = ConstantBootstraps.getStaticFinal(
        lookup, "LABEL", String.class, Settings.class);
Object limit = ConstantBootstraps.getStaticFinal(
        lookup, "LIMIT", int.class, Settings.class);
```

Chú ý:
- `"LABEL"` hoặc `"LIMIT"` là **tên field**, không phải tên class.
- `String.class` và `int.class` là **kiểu thật của field**, không phải `Object.class` chỉ vì phương thức bootstrap khai báo trả `Object`.
- `Settings.class` là **class khai báo field**.
- Giá trị `int` đi qua API có return type `Object` sẽ xuất hiện dưới dạng giá trị đã boxing, chẳng hạn `Integer.valueOf(17)` khi gọi trực tiếp từ Java.

### 5.2. Overload ba tham số: owner được suy từ type

```java
Object zero = ConstantBootstraps.getStaticFinal(
        MethodHandles.lookup(), "ZERO", java.math.BigInteger.class);
```

`BigInteger.ZERO` là static final field có kiểu `BigInteger` và được khai báo trong chính `BigInteger`. Vì vậy overload ngắn suy ra owner là `BigInteger.class`.

Đối với field **primitive**, overload ngắn suy owner là **wrapper class** của primitive đó, ví dụ kiểu `int.class` suy owner là `Integer.class` (nên có thể dùng các field phù hợp như `Integer.MAX_VALUE`).

**Không hiểu lầm:** `getStaticFinal(lookup,"LABEL",String.class)` **không** tìm khắp classpath một field `LABEL` có kiểu String. Nó chỉ xem class liên quan đến `type`; vì `LABEL` trong `Settings`, phải dùng overload **bốn tham số** để chỉ rõ owner.

### 5.3. Điều kiện field và lỗi linkage

| Tình huống | Kết quả điển hình |
| --- | --- |
| Field tồn tại, đúng kiểu, có `static final` và truy cập hợp lệ | Trả giá trị field |
| Tên field không có hoặc không resolve được với kiểu được yêu cầu | `NoSuchFieldError` |
| Field có tên/kiểu phù hợp nhưng **không final** | `IncompatibleClassChangeError` |
| Owner/field không accessible với `lookup` | `IllegalAccessError` |
| Class initialization thất bại trong đường truy cập | Có thể gặp lỗi liên quan initialization, ví dụ `ExceptionInInitializerError` |

Ở mức API `ConstantBootstraps`, các lỗi này có thể là **`Error` thuộc linkage**, không nên bắt rồi mặc định retry như một lỗi mạng. Nếu được dùng trong **resolution của dynamic constant**, JVM có thể ghi nhận kết quả thất bại cho symbolic reference ấy; sửa runtime state sau đó không bảo đảm reference đã fail sẽ tự resolve lại.

### 5.4. `static final` không đồng nghĩa object bất biến

Ví dụ `static final List<String> ITEMS = new ArrayList<>();`: field reference là `final` nhưng object `ArrayList` vẫn mutable. Nếu giá trị đó được đưa vào dynamic constant, **hằng tham chiếu** không có nghĩa danh sách được đóng băng. Ngoài ra, Java compiler có thể inline những `static final` compile-time constants trong Java source thông thường; liên kết qua `getStaticFinal` là một con đường khác, đừng nhầm với direct source-level constant inlining.

## 6. Bộ ba VarHandle bootstrap

`VarHandle` là API truy cập một biến theo **tọa độ** và **access mode**. `ConstantBootstraps` có ba phương thức tạo hằng trả **VarHandle**, chứ không trả giá trị đang nằm trong biến.

### 6.1. `fieldVarHandle` — instance field

Signature:

```java
VarHandle fieldVarHandle(
        MethodHandles.Lookup lookup,
        String name,
        Class<VarHandle> type,
        Class<?> declaringClass,
        Class<?> fieldType);
```

Ý nghĩa:
- `name`: tên field instance (ví dụ `"count"`).
- `type`: **kiểu của dynamic constant kết quả**, bắt buộc là `VarHandle.class`.
- `declaringClass`: class nơi khai báo field.
- `fieldType`: kiểu thực của biến (ví dụ `int.class`).

Với:

```java
static final class Counter {
    volatile int count;
}

VarHandle vh = ConstantBootstraps.fieldVarHandle(
        MethodHandles.lookup(), "count",
        VarHandle.class, Counter.class, int.class);

Counter c = new Counter();
vh.setVolatile(c, 3);
int current = (int) vh.getVolatile(c);
```

Đây là **đoạn minh họa**, cần đặt khai báo class và các statement trong ngữ cảnh Java hợp lệ. Vì là instance field, access mode như `getVolatile`, `setVolatile` hoặc `compareAndSet` cần **receiver** `Counter` làm tọa độ đầu tiên. Không được gọi `vh.getVolatile()` mà không truyền receiver.

### 6.2. `staticFieldVarHandle` — static field

Signature:

```java
VarHandle staticFieldVarHandle(
        MethodHandles.Lookup lookup,
        String name,
        Class<VarHandle> type,
        Class<?> declaringClass,
        Class<?> fieldType);
```

Với `static volatile long total;` trong class `Counter`:

```java
VarHandle totalVH = ConstantBootstraps.staticFieldVarHandle(
        MethodHandles.lookup(), "total",
        VarHandle.class, Counter.class, long.class);
totalVH.setVolatile(9L);
long total = (long) totalVH.getVolatile();
```

Đây là đoạn minh họa, với `Counter` có static field `total` phù hợp. Vì là **static field**, không cần receiver; danh sách tọa độ là rỗng. Sai số lượng/kiểu tham số khi gọi access mode của `VarHandle` có thể ném `WrongMethodTypeException`.

### 6.3. `arrayVarHandle` — phần tử array

Signature:

```java
VarHandle arrayVarHandle(
        MethodHandles.Lookup lookup,
        String name,
        Class<VarHandle> type,
        Class<?> arrayClass);
```

`name` ở đây **không được dùng** để chọn index hay field. `arrayClass` phải mô tả một array class như `int[].class` hoặc `String[].class`.

```java
VarHandle element = ConstantBootstraps.arrayVarHandle(
        MethodHandles.lookup(), "unused", VarHandle.class, int[].class);
int[] numbers = {2, 3};
element.setVolatile(numbers, 1, 8);
int value = (int) element.getVolatile(numbers, 1);
```

Đây là đoạn minh họa, chạy trong method đã import đủ các API. Tọa độ của array element là:
1. tham chiếu tới **mảng**;
2. chỉ số **index**;
3. sau đó mới tới giá trị mới nếu đang set/CAS.

`arrayVarHandle` mô tả **quy tắc truy cập phần tử** chứ không cố định một array object hay một chỉ số. Cùng VarHandle có thể dùng cho các instance khác nhau của `int[]`.

### 6.4. So sánh ba loại handle

| Loại biến | Ví dụ field/mảng | Tọa độ của access mode | Cách gọi `getVolatile` |
| --- | --- | --- | --- |
| Instance field | `Counter.count` | `(Counter receiver)` | `(int) vh.getVolatile(counter)` |
| Static field | `Counter.total` | Không có tọa độ receiver | `(long) vh.getVolatile()` |
| Array element | `int[]` | `(int[] array, int index)` | `(int) vh.getVolatile(array, i)` |

**Phân biệt `VarHandle.class` và `fieldType`:** Đối số `type` trong cả ba bootstrap là `VarHandle.class` vì **giá trị hằng tạo ra là một VarHandle**. Đối số `fieldType` chỉ xuất hiện ở field/static field bootstrap để xác định **kiểu biến được truy cập**. Không truyền nhầm `int.class` làm `type`.

### 6.5. Có thể liên kết VarHandle tới final field không?

Có thể có VarHandle với khả năng **đọc** một final field, nhưng các chế độ **ghi** (và một số update modes) không được hỗ trợ cho field final. `VarHandle.isAccessModeSupported(...)` giúp kiểm tra. Gọi access mode không được hỗ trợ có thể ném `UnsupportedOperationException`.

Việc bootstrap tạo ra một VarHandle **không cấp quyền vượt qua tính final hay Java Memory Model**. Nếu cần giá trị của field `static final` như một hằng, `getStaticFinal` thường diễn đạt mục tiêu rõ hơn; nếu cần một **handle truy cập**, dùng VarHandle bootstrap nhưng phải tuân theo semantics của field.

## 7. Từ bootstrap trực tiếp tới mô tả hằng động bằng `DynamicConstantDesc`

Java 17 có gói `java.lang.constant` cung cấp API **mô tả hằng** ở mức nominal, hữu ích cho công cụ phân tích/phát sinh class file.

Các lớp/chủ thể:
- `ClassDesc`: mô tả một class type trong constant pool.
- `ConstantDescs`: chứa các descriptor dựng sẵn cho bootstrap, như `BSM_NULL_CONSTANT`, `BSM_ENUM_CONSTANT`, `BSM_GET_STATIC_FINAL`, `BSM_VARHANDLE_FIELD`, `BSM_VARHANDLE_STATIC_FIELD`, `BSM_VARHANDLE_ARRAY`.
- `DynamicConstantDesc<?>`: mô tả **bootstrap method + name + constant type + static arguments** của một dynamic constant.
- `resolveConstantDesc(lookup)`: **mô phỏng resolution bằng reflection** trong context cung cấp; **không có bộ nhớ đệm** kết quả như symbolic reference trong JVM run-time constant pool.

### 7.1. Mô tả null constant

```java
DynamicConstantDesc<?> desc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_NULL_CONSTANT,
        ConstantDescs.DEFAULT_NAME,
        ConstantDescs.CD_String);

Object value = desc.resolveConstantDesc(MethodHandles.lookup());
// value == null
```

Đây là đoạn minh họa cần import `DynamicConstantDesc`, `ConstantDescs`, `MethodHandles` và xử lý checked exception từ `resolveConstantDesc`. `DEFAULT_NAME` phù hợp vì `nullConstant` **không sử dụng name**.

### 7.2. Mô tả enum constant

```java
DynamicConstantDesc<?> enumDesc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_ENUM_CONSTANT,
        "MONDAY",
        ClassDesc.of("java.time.DayOfWeek"));

Object monday = enumDesc.resolveConstantDesc(MethodHandles.lookup());
// monday == java.time.DayOfWeek.MONDAY
```

`name` chính là `"MONDAY"`, còn `constantType` được mô tả bằng `ClassDesc` trỏ tới enum class. Descriptor không cần static arg cho bootstrap `enumConstant`.

### 7.3. Mô tả static final field: **static arg owner bắt buộc**

```java
DynamicConstantDesc<?> finalDesc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_GET_STATIC_FINAL,
        "ZERO",
        ClassDesc.of("java.math.BigInteger"),
        ClassDesc.of("java.math.BigInteger"));

Object zero = finalDesc.resolveConstantDesc(MethodHandles.lookup());
// zero == BigInteger.ZERO (so sánh bằng identity trong trường hợp này)
```

Ở đây **ClassDesc thứ nhất** là **kiểu của hằng** (`BigInteger`). **ClassDesc thứ hai** là **static bootstrap argument mô tả owner** (`BigInteger`). Cần cả hai.

**Bẫy rất hay gặp:** `ConstantBootstraps.getStaticFinal(lookup, name, type)` **có overload trực tiếp ba tham số**, nhưng descriptor dựng sẵn `ConstantDescs.BSM_GET_STATIC_FINAL` mô tả **overload có declaringClass**. Khi dùng `DynamicConstantDesc.ofNamed` với descriptor này, **không được bỏ static arg owner**; nếu thiếu, resolution thất bại vì bootstrap method handle nhận sai số đối số, thường thấy dưới dạng `BootstrapMethodError`.

### 7.4. Mô tả array VarHandle

```java
DynamicConstantDesc<?> arrayDesc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_VARHANDLE_ARRAY,
        ConstantDescs.DEFAULT_NAME,
        ConstantDescs.CD_VarHandle,
        ConstantDescs.CD_int.arrayType());

VarHandle element = (VarHandle)
        arrayDesc.resolveConstantDesc(MethodHandles.lookup());
```

Ở đây:
- `CD_VarHandle` là **kiểu của kết quả hằng**;
- `CD_int.arrayType()` là **static arg array class `int[]`**;
- bootstrap `arrayVarHandle` bỏ qua name.

### 7.5. Mô tả instance-field VarHandle

```java
DynamicConstantDesc<?> fieldDesc = DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_VARHANDLE_FIELD,
        "count",
        ConstantDescs.CD_VarHandle,
        ClassDesc.of("ConstantBootstrapsGuide$State"),
        ConstantDescs.CD_int);
```

Đây là đoạn minh họa dành cho nested class `State` của chương trình bên dưới. Thứ tự các static arguments là **declaring class** rồi **field type**. `ClassDesc.of("ConstantBootstrapsGuide$State")` mô tả **binary name** của nested class; ký tự `$` ở đây là thành phần của tên nhị phân, không phải cú pháp Java để truy cập member.

Trong những hệ thống có module và class loader phức tạp, descriptor cần resolve trong `Lookup` phù hợp. Tên lớp trùng chuỗi nhưng do hai class loader khác nhau nạp không phải cùng một `Class` identity.

### 7.6. Descriptor không phải bytecode `ldc`

Bốn ví dụ `DynamicConstantDesc` ở trên **không tự tạo một `CONSTANT_Dynamic_info` trong class file** của chương trình demo. Việc gọi `resolveConstantDesc` tính giá trị bằng API phản chiếu để kiểm thử hoặc làm công cụ. Muốn có dynamic constant thật được load qua `ldc`, class file cần có **constant-pool entry đúng cấu trúc** với `BootstrapMethods` và instruction/đường sử dụng phù hợp; một bytecode generation library hoặc class-file tooling mới có thể phát sinh cấu trúc đó.

**Khác biệt quan trọng:** JVM cache resolution theo symbolic reference; `DynamicConstantDesc.resolveConstantDesc` công khai rằng **không cache** giá trị trả về. Nếu dùng API mô phỏng để đo tốc độ “conDy được cache ở runtime”, kết quả sẽ sai mục tiêu đo.

## 8. Chương trình Java 17+ hoàn chỉnh, đã kiểm chứng

Chương trình sau minh họa đủ bốn họ chức năng: `nullConstant`, `enumConstant`, `getStaticFinal`, ba VarHandle bootstrap và các **nominal descriptors** tương ứng. Có cả trường hợp lỗi để thấy contract.

Lưu file **`ConstantBootstrapsGuide.java`**:

```java
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;
import java.lang.constant.DynamicConstantDesc;
import java.lang.invoke.ConstantBootstraps;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.math.BigInteger;

public class ConstantBootstrapsGuide {
    enum Mode { FAST, SLOW }

    static final class State {
        static final String LABEL = "ready";
        static final int LIMIT = 17;
        static int editable = 5;
        static volatile long global;
        volatile int count;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        Object nil = ConstantBootstraps.nullConstant(lookup, "unused", String.class);
        System.out.println("null=" + (nil == null));
        try {
            ConstantBootstraps.nullConstant(lookup, "unused", int.class);
        } catch (IllegalArgumentException expected) {
            System.out.println("nullPrimitive=" + expected.getClass().getSimpleName());
        }

        Mode enumValue = ConstantBootstraps.enumConstant(lookup, "FAST", Mode.class);
        System.out.println("enum=" + enumValue);
        try {
            ConstantBootstraps.enumConstant(lookup, "MISSING", Mode.class);
        } catch (IllegalArgumentException expected) {
            System.out.println("enumMissing=" + expected.getClass().getSimpleName());
        }

        Object label = ConstantBootstraps.getStaticFinal(
                lookup, "LABEL", String.class, State.class);
        Object limit = ConstantBootstraps.getStaticFinal(
                lookup, "LIMIT", int.class, State.class);
        Object zero = ConstantBootstraps.getStaticFinal(
                lookup, "ZERO", BigInteger.class);
        System.out.println("staticLabel=" + label);
        System.out.println("staticLimit=" + limit);
        System.out.println("shortFinal=" + zero);

        try {
            ConstantBootstraps.getStaticFinal(
                    lookup, "editable", int.class, State.class);
        } catch (IncompatibleClassChangeError expected) {
            System.out.println("nonFinal=" + expected.getClass().getSimpleName());
        }

        State state = new State();
        VarHandle field = ConstantBootstraps.fieldVarHandle(
                lookup, "count", VarHandle.class, State.class, int.class);
        field.setVolatile(state, 4);
        boolean changed = field.compareAndSet(state, 4, 5);
        System.out.println("instanceCAS=" + changed);
        System.out.println("instance=" + (int) field.getVolatile(state));

        VarHandle stat = ConstantBootstraps.staticFieldVarHandle(
                lookup, "global", VarHandle.class, State.class, long.class);
        stat.setVolatile(9L);
        System.out.println("staticVar=" + (long) stat.getVolatile());

        VarHandle array = ConstantBootstraps.arrayVarHandle(
                lookup, "unused", VarHandle.class, int[].class);
        int[] numbers = {2, 3};
        array.setVolatile(numbers, 1, 8);
        System.out.println("array=" + (int) array.getVolatile(numbers, 1));

        DynamicConstantDesc<?> nullDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_NULL_CONSTANT,
                ConstantDescs.DEFAULT_NAME,
                ConstantDescs.CD_String);
        System.out.println("descNull=" + (nullDesc.resolveConstantDesc(lookup) == null));

        DynamicConstantDesc<?> enumDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_ENUM_CONSTANT,
                "MONDAY",
                ClassDesc.of("java.time.DayOfWeek"));
        System.out.println("descEnum=" + enumDesc.resolveConstantDesc(lookup));

        DynamicConstantDesc<?> finalDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_GET_STATIC_FINAL,
                "ZERO",
                ClassDesc.of("java.math.BigInteger"),
                ClassDesc.of("java.math.BigInteger"));
        System.out.println("descFinal=" + finalDesc.resolveConstantDesc(lookup));

        DynamicConstantDesc<?> arrayDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_VARHANDLE_ARRAY,
                ConstantDescs.DEFAULT_NAME,
                ConstantDescs.CD_VarHandle,
                ConstantDescs.CD_int.arrayType());
        VarHandle descArrayVH = (VarHandle) arrayDesc.resolveConstantDesc(lookup);
        System.out.println("descArray=" + (int) descArrayVH.getVolatile(numbers, 1));

        DynamicConstantDesc<?> fieldDesc = DynamicConstantDesc.ofNamed(
                ConstantDescs.BSM_VARHANDLE_FIELD,
                "count",
                ConstantDescs.CD_VarHandle,
                ClassDesc.of("ConstantBootstrapsGuide$State"),
                ConstantDescs.CD_int);
        VarHandle descFieldVH = (VarHandle) fieldDesc.resolveConstantDesc(lookup);
        System.out.println("descField=" + (int) descFieldVH.getVolatile(state));
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac --release 17 ConstantBootstrapsGuide.java
java ConstantBootstrapsGuide
```

**Stdout đã kiểm chứng với bản Java tương thích Java 17:**

```text
null=true
nullPrimitive=IllegalArgumentException
enum=FAST
enumMissing=IllegalArgumentException
staticLabel=ready
staticLimit=17
shortFinal=0
nonFinal=IncompatibleClassChangeError
instanceCAS=true
instance=5
staticVar=9
array=8
descNull=true
descEnum=MONDAY
descFinal=0
descArray=8
descField=5
```

### 8.1. Giải thích nhóm null/enum

- `null=true` chứng tỏ bootstrap trả reference `null` cho `String.class`.
- `nullPrimitive=IllegalArgumentException` chứng tỏ primitive `int.class` không phải type được phép.
- `enum=FAST` là giá trị enum đã chọn bằng **tên chính xác**.
- `enumMissing=IllegalArgumentException` minh họa không có phần tử tên `MISSING`; bootstrap không tự chọn default.

### 8.2. Giải thích nhóm static final

- `staticLabel=ready` đến từ `State.LABEL` qua overload có owner tường minh.
- `staticLimit=17` đến từ field `int LIMIT`; method bootstrap có return `Object` nên kết quả được boxing khi trả qua Java API.
- `shortFinal=0` dùng overload **ba tham số** để lấy `BigInteger.ZERO`, vì owner và field type là `BigInteger`.
- `nonFinal=IncompatibleClassChangeError` cho thấy field `editable` không phải `final`. Chương trình chủ động catch loại `Error` này **chỉ để minh họa**, không phải lời khuyên nuốt lỗi linkage trong ứng dụng production.

### 8.3. Giải thích nhóm VarHandle

- `instanceCAS=true`: VarHandle của instance field `count` thực hiện CAS từ `4` sang `5`.
- `instance=5`: cùng handle đọc giá trị mới qua receiver `state`.
- `staticVar=9`: VarHandle static field `global` **không cần receiver**.
- `array=8`: array VarHandle ghi phần tử thứ hai của `int[]`; cần array và index.

Các thao tác này cập nhật **biến được VarHandle trỏ tới**, chứ không thay giá trị hằng dynamic nếu một VarHandle đã được liên kết thành constant. Hằng giữ object handle; handle vẫn có thể thực hiện truy cập vào trạng thái đang đổi.

### 8.4. Giải thích nhóm DynamicConstantDesc

- `descNull=true`: `BSM_NULL_CONSTANT` mô phỏng resolution và trả `null`.
- `descEnum=MONDAY`: `BSM_ENUM_CONSTANT` dùng name và enum class descriptor.
- `descFinal=0`: `BSM_GET_STATIC_FINAL` nhận **owner ClassDesc làm static arg** như yêu cầu.
- `descArray=8`: array VarHandle descriptor được resolve thành VarHandle, sau đó đọc array đã cập nhật.
- `descField=5`: field VarHandle descriptor được resolve, sau đó đọc instance field `count` của `state`.

**Lưu ý về exception declaration:** `main throws ReflectiveOperationException` chỉ để ví dụ tập trung vào resolution. Trong công cụ thực, cần xử lý đúng các lỗi access/lookup/descriptor và `LinkageError`, thay vì xem tất cả là lỗi dữ liệu thông thường.

## 9. Tại sao “giá trị hằng” và “biến được VarHandle trỏ tới” rất khác nhau?

Một dynamic constant có thể resolve thành:

1. `null` cho một reference type.
2. Một **enum singleton**.
3. **Giá trị hiện tại** được lấy từ một field `static final` tại resolution.
4. Một object `VarHandle` đại diện cho **quy tắc truy cập biến**.

Trường hợp (4) khác hẳn (3):

```text
CONSTANT_Dynamic -> bootstrap fieldVarHandle
                 -> VarHandle object (được xem là giá trị hằng)
                 -> truy cập Counter.count hiện tại qua receiver
                 -> giá trị count có thể đổi theo thời gian
```

Không vì VarHandle được cung cấp qua constant pool mà field biến thành `final` hoặc biến bị đóng băng. Với một `VarHandle` tới `volatile int count`, mỗi lần `getVolatile(receiver)` vẫn thực hiện truy cập volatile theo hợp đồng `VarHandle`. Constant pool cache object `VarHandle`, không cache kết quả mỗi lần gọi `getVolatile`.

Ngược lại, một dynamic constant resolve thành **giá trị** `static final` không biến thành “live observer” của field. Điều này đặc biệt dễ nhầm khi các test thay đổi state bằng kỹ thuật không chuẩn; Java không hứa `static final` field có thể được sửa tùy tiện sau initialization.

## 10. Quyền truy cập và lỗi khi bootstrap chạy

### 10.1. `Lookup` là ngữ cảnh security, không phải wildcard

`MethodHandles.Lookup` đại diện quyền của class gọi trong ngữ cảnh thích hợp. Bootstrap làm việc trên field/enum vẫn phải tuân theo access checks, class loader identity và module boundaries.

Trong ví dụ đầy đủ, `State` và `Mode` là các type lồng trong `ConstantBootstrapsGuide`, và `MethodHandles.lookup()` được tạo trong class ngoài. Đây là cùng **nest** theo Java hiện đại, cho phép ví dụ truy cập field đúng. Nếu bạn thay `State` bằng class trong module khác không xuất package hoặc không cho phép quyền truy cập, resolution có thể thất bại.

Không sử dụng `privateLookupIn`, `setAccessible(true)` hoặc lookup full-power như một giải pháp “bypass security” chung. Chỉ tạo lookup đúng quyền theo hợp đồng. Một class file độc hại không được phép tự dùng bootstrap để đọc private field của class không cấp quyền.

### 10.2. Các lỗi hay gặp

| API hoặc pha | Ví dụ sai | Loại lỗi quan trọng |
| --- | --- | --- |
| `nullConstant` | `type=int.class` hoặc `void.class` | `IllegalArgumentException` |
| `enumConstant` | Tên enum không tồn tại hoặc type không phải enum | `IllegalArgumentException` |
| `getStaticFinal` | Sai tên/field signature | `NoSuchFieldError` |
| `getStaticFinal` | Field có giá trị nhưng không `final` | `IncompatibleClassChangeError` |
| `getStaticFinal` / field bootstrap | Thiếu access tới owner/field | `IllegalAccessError` |
| `fieldVarHandle` | Tên/kiểu field không phù hợp | `NoSuchFieldError` |
| `staticFieldVarHandle` | Không resolve được static field phù hợp | `NoSuchFieldError` hoặc lỗi linkage thích hợp |
| `arrayVarHandle` | Truyền class không phải array | Lỗi không hợp lệ đầu vào, thường `IllegalArgumentException` |
| Một trong ba VarHandle bootstrap | `type` không phải `VarHandle.class` | `IllegalArgumentException` |
| Gọi VarHandle access mode | Sai số lượng/kiểu tọa độ hoặc value | Thường `WrongMethodTypeException` |
| Gọi access mode không hỗ trợ | Cố set final field | `UnsupportedOperationException` |
| `DynamicConstantDesc.resolveConstantDesc` | Thiếu bootstrap argument bắt buộc | Có thể `BootstrapMethodError`/`WrongMethodTypeException` theo đường resolution |
| Actual JVM condy resolution | Bootstrap ném checked/unchecked exception không phải `Error` | `BootstrapMethodError` bọc nguyên nhân |
| Actual JVM condy resolution | Bootstrap tự ném `Error` | JVM có thể truyền chính `Error` đó theo đặc tả |

**Phân biệt hai nhóm lỗi:**
- **Direct Java call** tới `ConstantBootstraps`: caller nhận lỗi theo **hợp đồng trực tiếp của method**.
- **JVM resolution của dynamic constant**: JVM áp dụng thêm **quy tắc linkage/validation của `CONSTANT_Dynamic_info`**; exception không thuộc `Error` từ việc gọi bootstrap được bao bởi `BootstrapMethodError`, còn lỗi kiểu kết quả có thể thành `BootstrapMethodError`.

Không thử “retry mãi” một symbolic reference đã lỗi vì JVM có thể cache kết quả thất bại của resolution. Nếu lỗi do cấu hình/deployment, sửa nguyên nhân và triển khai lại class/version phù hợp thay vì kỳ vọng constant pool tự liên kết lại.

### 10.3. Kết quả bootstrap phải hợp kiểu hằng

Nếu dynamic constant khai báo field type `String`, bootstrap phải đưa ra giá trị reference tương thích `String` hoặc `null`. Nếu type là `int`, kết quả bootstrap phải được chuyển đổi theo rules JVM tới `int`; `null` không phải kết quả hợp lệ và có thể gây `BootstrapMethodError` trong validation.

Đừng chỉ nhìn return type khai báo `Object` của `getStaticFinal` rồi kết luận constant luôn có type `Object`: kiểu hằng thật do **descriptor** yêu cầu. Bootstrap chỉ là mã tính giá trị; JVM phải kiểm tra kết quả.

## 11. Quy trình thiết kế conDy an toàn trong công cụ bytecode/runtime

Một công cụ tạo class file có thể tuân theo quy trình:

1. **Chọn đúng mục tiêu:** muốn một **giá trị hằng** hay một **handle để truy cập biến**? Nếu cần truy cập field đang thay đổi, chọn VarHandle bootstrap.
2. **Chọn bootstrap chuẩn:** null/enum/static-final/field/static-field/array, thay vì tự tạo bootstrap phức tạp không cần thiết.
3. **Xác định constant name và field descriptor:** `enumConstant`/field bootstrap cần tên chính xác; `nullConstant`/`arrayVarHandle` không dùng name.
4. **Xác định static args:** với `BSM_GET_STATIC_FINAL` và `BSM_VARHANDLE_FIELD`, truyền **owner class** và các type descriptors đúng thứ tự.
5. **Xác thực class loader và access:** mỗi owner/component type phải resolve được và có quyền hợp lệ.
6. **Kiểm tra return type:** giá trị do bootstrap tính ra phải phù hợp field descriptor; riêng VarHandle bootstrap có constant type là `VarHandle`.
7. **Không đặt side effect không idempotent trong bootstrap:** concurrent resolution có thể gọi bootstrap hơn một lần trước khi JVM chọn một kết quả.
8. **Kiểm thử trực tiếp và mô phỏng:** test API `ConstantBootstraps` và `DynamicConstantDesc.resolveConstantDesc` trên JDK mục tiêu để bắt lỗi args/type.
9. **Kiểm thử class file thật:** nếu generator thật tạo `CONSTANT_Dynamic_info`, dùng công cụ inspect class file và một integration test **thực thi `ldc`** để kiểm tra linkage và caching.
10. **Quan sát lỗi đúng lớp:** log đủ tên hằng, descriptor, owner, bootstrap method, static args và cause; không “đoán” lỗi là application exception khi thật ra là linkage failure.

### 11.1. Vì sao cần hai loại test?

Một test gọi trực tiếp `getStaticFinal(...)` giúp xác nhận tên/kiểu/owner có hợp lệ. Nhưng nó **không xác minh**:
- class file chứa `CONSTANT_Dynamic_info` và `BootstrapMethods` đúng index;
- compiler/generator ghi đúng field descriptor;
- JVM xử lý resolution caching/failure caching;
- bytecode `ldc` thực sự tham chiếu đúng symbolic reference.

Do đó với dự án tạo class file, cần cả unit test bootstrap API và integration test classfile/JVM resolution. Ví dụ Java thuần ở phần 8 cố ý **không hứa** nó đã phát sinh conDy thật.

### 11.2. Lựa chọn giữa các API tương đương

| Nhu cầu | API hợp lý |
| --- | --- |
| Dùng `null` trong Java code thông thường | `null` literal, không cần bootstrap |
| Lấy enum constant từ chuỗi ở application logic | `Enum.valueOf(...)` nếu phù hợp |
| Đọc field `static final` trong Java source | Truy cập field bình thường với quyền thích hợp |
| Tạo một `VarHandle` trong code runtime | `MethodHandles.Lookup.findVarHandle/findStaticVarHandle` hoặc `arrayElementVarHandle` |
| Mô tả conDy trong tooling | `ConstantDescs` + `DynamicConstantDesc` |
| Bootstrap một `CONSTANT_Dynamic_info` trong class file | `ConstantBootstraps` chuẩn cùng descriptors/static args đúng |

Các API trực tiếp như `Lookup.findVarHandle` có thể báo **`NoSuchFieldException` / `IllegalAccessException`** lúc lookup, trong khi `ConstantBootstraps.fieldVarHandle` có hợp đồng **linkage errors** như `NoSuchFieldError` / `IllegalAccessError`. Chọn API theo ngữ cảnh, đừng xem chúng có cùng hệ thống exception mặc định.

## 12. Những hiểu sai thường gặp

1. **“Gọi `ConstantBootstraps.nullConstant` trong Java nghĩa là đã dùng `CONSTANT_Dynamic_info`.”** Sai. Đó có thể chỉ là một method call thông thường.
2. **“DynamicConstantDesc.resolveConstantDesc tự cache giống JVM conDy.”** Sai. Phương thức này mô phỏng resolution **không cache**.
3. **“Bootstrap của mỗi conDy chắc chắn chỉ chạy đúng một lần trong mọi race.”** Không hẳn; JVM có thể cho nhiều thread chạy bootstrap đồng thời trước khi chọn kết quả.
4. **“Null constant có thể dùng `int.class` và được biến thành 0.”** Sai. `nullConstant` chỉ chấp nhận reference type.
5. **“`enumConstant` bỏ qua name vì đã biết Enum.class.”** Sai. `name` quyết định enum constant.
6. **“`getStaticFinal` overload ngắn tìm field ở class chứa caller.”** Sai. Owner suy theo `type`/wrapper class.
7. **“`getStaticFinal` nhận fieldType Object.class vì method trả Object.”** Sai. `type` phải phản ánh kiểu field thực.
8. **“`BSM_GET_STATIC_FINAL` trong `ConstantDescs` luôn đủ ba tham số implicit.”** Sai. Descriptor dựng sẵn cần **static arg declaring class**.
9. **“`fieldVarHandle` có `type=int.class` vì field là int.”** Sai. Constant type phải là `VarHandle.class`; `fieldType=int.class` là tham số riêng.
10. **“Array VarHandle được tạo cho một array instance/index cụ thể.”** Sai. Nó mô tả array class và nhận array/index lúc access.
11. **“Static VarHandle cần truyền receiver khi get/set.”** Sai. Static field không có receiver coordinate.
12. **“Một hằng VarHandle nghĩa là field nó trỏ đến cũng immutable.”** Sai. Field có semantics riêng; access mode có thể đọc/ghi theo policy.
13. **“VarHandle tới final field có thể set nếu bootstrap chạy từ code có quyền.”** Sai. Access mode ghi final field vẫn không được hỗ trợ.
14. **“Khi conDy resolve lỗi thì lần `ldc` sau tự thử bootstrap lại.”** Sai. JVM duy trì kết quả thất bại của symbolic reference theo quy tắc resolution.
15. **“Nếu mô phỏng descriptor chạy được thì class file chắc chắn hợp lệ.”** Sai. Cần kiểm thử cấu trúc classfile thật, bootstrap method handle, static args và bytecode.
16. **“Có thể dùng quyền của bất kỳ Lookup để đọc field private của module khác.”** Sai. Access checks vẫn phải thỏa.
17. **“Hằng động giống invokedynamic, bootstrap trả CallSite.”** Sai. Condy trả một giá trị phù hợp field type; indy trả CallSite.

## 13. Bài tập và đáp án

### Bài 1 — Phân biệt kiểu null

Hãy xác định trường hợp nào hợp lệ:

```java
ConstantBootstraps.nullConstant(lookup, "x", String.class);
ConstantBootstraps.nullConstant(lookup, "x", int.class);
ConstantBootstraps.nullConstant(lookup, "x", Void.class);
ConstantBootstraps.nullConstant(lookup, "x", void.class);
```

Đây là đoạn minh họa với `lookup` đã được khởi tạo trong method.

**Đáp án:** `String.class` và `Void.class` là reference types nên hợp lệ và trả `null`. `int.class`, `void.class` không hợp lệ và ném `IllegalArgumentException`.

### Bài 2 — Tìm đúng overload static final

Cho:

```java
class Config {
    static final String REGION = "APAC";
}
```

Muốn lấy `Config.REGION` qua `ConstantBootstraps` khi `lookup` có quyền, dùng overload nào?

**Đáp án:** Dùng **bốn tham số**:

```java
Object region = ConstantBootstraps.getStaticFinal(
        lookup, "REGION", String.class, Config.class);
```

Không dùng overload ngắn vì `String.class` không phải owner của `Config.REGION`.

### Bài 3 — Suy luận kiểu VarHandle

`ConstantBootstraps.fieldVarHandle(lookup,"count",VarHandle.class,Counter.class,int.class)` trả về object gì? Khi gọi `getVolatile` cần những tọa độ nào?

**Đáp án:** Trả một **`VarHandle`** tới instance field `Counter.count` kiểu `int`. Cần receiver `Counter`, ví dụ `(int) vh.getVolatile(counter)`. Nó không trả `int` value ngay khi liên kết.

### Bài 4 — Static argument của BSM_GET_STATIC_FINAL

Có descriptor:

```java
DynamicConstantDesc.ofNamed(
        ConstantDescs.BSM_GET_STATIC_FINAL,
        "ZERO",
        ClassDesc.of("java.math.BigInteger"));
```

Điều gì còn thiếu?

**Đáp án:** Thêm **static bootstrap argument** `ClassDesc.of("java.math.BigInteger")` cho **declaring class**. `BSM_GET_STATIC_FINAL` dựng sẵn tham chiếu overload cần owner; nếu bỏ có thể gây lỗi bootstrap method type/arity.

### Bài 5 — Constant pool và trạng thái mutable

Một `CONSTANT_Dynamic_info` resolve thành `VarHandle` cho `State.global`. Sau đó thread khác cập nhật field bằng `setVolatile`. Khi gọi `getVolatile` qua VarHandle đã resolve, có nhận giá trị mới không?

**Đáp án:** VarHandle là **handle tới biến**, không phải bản sao giá trị field. Các lần truy cập tiếp theo vẫn tuân theo access-mode memory semantics và có thể quan sát cập nhật theo các bảo đảm memory ordering phù hợp. Constant pool không “đóng băng” field value.

### Bài 6 — Nhận diện sai mục tiêu kiểm thử

Một test gọi `desc.resolveConstantDesc(lookup)` hai lần, thấy bootstrap chạy hai lần, rồi kết luận JVM conDy không cache. Kết luận đó có đúng không?

**Đáp án:** Không. `resolveConstantDesc` **không cache** khi mô phỏng resolution. Muốn kiểm thử cache của **JVM run-time constant pool**, phải dùng một class file có `CONSTANT_Dynamic_info` thực sự và làm JVM resolve chính entry ấy.

### Bài 7 — Lỗi khi cập nhật field final

Một generator tạo hằng VarHandle tới `static final int LIMIT` rồi cố `setVolatile(10)`. Vì sao sai?

**Đáp án:** VarHandle có thể hỗ trợ đọc field final, nhưng các access modes ghi không được hỗ trợ; tạo handle không bỏ qua `final`. Nên dùng `getStaticFinal` nếu mục tiêu là đọc hằng, hoặc dùng một field có thiết kế mutable thích hợp nếu cần cập nhật.

## Tài liệu chính thức

- [Java SE 17 API — ConstantBootstraps](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): signatures, điều kiện và lỗi của `nullConstant`, `enumConstant`, `getStaticFinal` và VarHandle bootstraps.
- [Java SE 17 API — ConstantDescs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ConstantDescs.html): bootstrap method descriptors dựng sẵn.
- [Java SE 17 API — DynamicConstantDesc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/DynamicConstantDesc.html): `ofNamed` và `resolveConstantDesc`, bao gồm quy tắc **không cache** khi mô phỏng.
- [Java SE 17 API — VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): tọa độ, access modes, memory semantics.
- [JVMS 17 — `4.4.10, CONSTANT_Dynamic_info và CONSTANT_InvokeDynamic_info](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10): cấu trúc pool entry.
- [JVMS 17 — `5.4.3.6, Dynamic Constant and Call Site Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): cách gọi bootstrap, caching, đồng thời và kiểm tra kết quả.

## Kết luận

`ConstantBootstraps` cung cấp những bootstrap chuẩn để tạo **hằng động**: `nullConstant` trả `null` cho reference type, `enumConstant` chọn enum theo name, `getStaticFinal` đọc giá trị của một field `static final`, còn `fieldVarHandle` / `staticFieldVarHandle` / `arrayVarHandle` trả **VarHandle** để truy cập biến theo tọa độ. Khi tạo descriptor, phải phân biệt rõ **type của hằng**, **owner** và các **static bootstrap arguments** — đặc biệt `BSM_GET_STATIC_FINAL` đòi hỏi owner arg. `DynamicConstantDesc.resolveConstantDesc` giúp mô phỏng, nhưng không thay thế kiểm thử **`CONSTANT_Dynamic_info` được JVM resolve qua bytecode thật**. Hiểu ranh giới này giúp thiết kế runtime/bytecode generator đúng kiểu, đúng quyền, đúng semantics lỗi và tránh nhầm việc cache giá trị hằng với đóng băng trạng thái object.
