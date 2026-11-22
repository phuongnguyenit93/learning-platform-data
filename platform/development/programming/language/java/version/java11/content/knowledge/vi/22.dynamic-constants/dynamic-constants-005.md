# Constant pool và BootstrapMethods: cách hằng số động được liên kết trong Java 11+

## 1. Vì sao một "hằng số" lại cần bootstrap method?

Khi đọc một file `.class`, ta thường thấy `constant_pool` chứa chuỗi, số, tên class, field/method references và các mô tả kiểu. Với các constant tĩnh thông thường, giá trị đã có trong file class hoặc JVM biết cách tạo nó trực tiếp từ metadata.

Từ **Java 11**, **JEP 309 — Dynamic Class-File Constants** bổ sung một dạng entry mới: **`CONSTANT_Dynamic_info`** (thường gọi tắt là *condy*). Thay vì ghi sẵn giá trị, class file ghi **công thức để JVM tính giá trị bằng một bootstrap method** tại thời điểm symbolic reference được resolve.

```text
Bytecode: ldc #19
        |
        v
constant_pool[#19] = CONSTANT_Dynamic
        |          name = GREETING
        |          descriptor = Ljava/lang/String;
        |          bootstrap_method_attr_index = 0
        v
ClassFile.attributes["BootstrapMethods"].bootstrap_methods[0]
        |
        +-- bootstrap_method_ref = MethodHandle tới Bootstrap.make
        +-- static arguments = "item-", 17
        |
        v
JVM invoke bootstrap(Lookup, "GREETING", String.class, "item-", 17)
        |
        v
Giá trị String "item-GREETING:17" được resolve và đặt lên operand stack.
```

Hai phần dữ liệu phải hiểu cùng nhau:

- **`constant_pool`** định danh một dynamic constant cần tính, với **tên, kiểu** và một **chỉ số bootstrap entry**.
- **`BootstrapMethods`** là **attribute cấp toàn class file** chứa danh sách các **method handles** và **static arguments** để JVM thực hiện việc bootstrap.

Giá trị có thể là reference, primitive, object tạo ở runtime hoặc một object như `VarHandle` nếu bootstrap được thiết kế phù hợp. Điều này không đồng nghĩa JVM tự động lưu một constant mới vào **source code** hay biến nó thành `static final` field.

**Phạm vi:** cấu trúc JVMS Java 11 (`CONSTANT_Dynamic` tag **17**, class-file major **55**) và các API vẫn áp dụng trên JDK hiện hành; không dựa vào cơ chế incubator cũ. Bài tập chính dùng Java 11 chạy được, có `javac --release 11`, tự tạo class file chứa condy và kiểm tra bằng `javap -v`.

## 2. Phân biệt `constant_pool` trong file và run-time constant pool

### 2.1. Class-file constant pool là bảng entry được đánh số

Cấu trúc tổng quát của `ClassFile`:

```text
ClassFile {
    u4 magic;              // 0xCAFEBABE
    u2 minor_version;
    u2 major_version;      // 55 khi target Java 11
    u2 constant_pool_count;
    cp_info constant_pool[constant_pool_count - 1];
    u2 access_flags;
    u2 this_class;
    u2 super_class;
    u2 interfaces_count;
    ...
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
```

Với `constant_pool_count = 23`, bảng có các **index từ 1 đến 22** trong ví dụ dùng những entry một slot. **Index 0 không được dùng để trỏ một cp_info thông thường**. `constant_pool_count` là số entry cộng 1 về mặt index-space, không phải số bytes chứa trong pool.

Lưu ý đặc biệt: `CONSTANT_Long` và `CONSTANT_Double` chiếm **hai vị trí index** trong constant-pool table theo đặc tả, dù cấu trúc entry có một giá trị. Vị trí ngay sau chúng là vị trí không thể được tham chiếu như một entry độc lập. Vì vậy không suy ngược số entry thực từ `constant_pool_count - 1` mà quên quy tắc này.

Trong class file, số nguyên nhiều byte `u2` và `u4` được lưu **big-endian**. Các field `u1/u2/u4` là dạng số unsigned với kích thước 1/2/4 byte.

### 2.2. Run-time constant pool

JVM tạo **run-time constant pool** tương ứng với mỗi class/interface được load. Nó chứa giá trị static và các **symbolic references** cần resolve: class, field, method, method handle, dynamic constant, invokedynamic call site...

```text
Đọc class file → tạo run-time constant pool → resolve symbolic reference khi cần
                                      |
                            Dynamic constant?
                                      |
                                      v
                       Chọn BSM + resolve static args
                                      |
                                      v
                         Invoke BSM, kiểm tra type
                                      |
                                      v
                           Lưu kết quả resolution
```

Có thể JVM thực hiện một số resolution sớm hoặc muộn miễn giữ ngữ nghĩa quan sát được theo JVMS. Với dynamic constant, **không coi bootstrap được gọi chỉ vì chương trình mới load class**. Khi một `ldc` thực sự yêu cầu một constant chưa resolve, bootstrap là một phần của quá trình resolution.

### 2.3. Những loại entry liên quan

| Constant-pool entry | Tag | Công dụng |
| --- | ---: | --- |
| `CONSTANT_Utf8` | 1 | Lưu tên, descriptor, chuỗi metadata |
| `CONSTANT_Integer` / `CONSTANT_Float` | 3 / 4 | Giá trị primitive cố định |
| `CONSTANT_Long` / `CONSTANT_Double` | 5 / 6 | Giá trị 64-bit, chiếm hai cp slots |
| `CONSTANT_Class` | 7 | Symbolic class/interface/array type |
| `CONSTANT_String` | 8 | String constant thông thường |
| `CONSTANT_Fieldref` | 9 | Symbolic reference tới field |
| `CONSTANT_Methodref` / `InterfaceMethodref` | 10 / 11 | Symbolic reference tới method |
| `CONSTANT_NameAndType` | 12 | Ghép một tên với descriptor |
| `CONSTANT_MethodHandle` | 15 | Handle mô tả cách truy cập field/method |
| `CONSTANT_MethodType` | 16 | Method type descriptor |
| **`CONSTANT_Dynamic`** | **17** | **Giá trị hằng được tính bằng bootstrap khi resolve** |
| **`CONSTANT_InvokeDynamic`** | **18** | **Call site được liên kết bằng bootstrap** |
| `CONSTANT_Module` / `CONSTANT_Package` | 19 / 20 | Metadata của module/package |

Cả `CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic` đều dùng **`BootstrapMethods`**, nhưng **không thể thay chúng cho nhau**: một entry cho **giá trị**, entry kia cho **lời gọi động**.

## 3. Định dạng nhị phân của `CONSTANT_Dynamic_info`

Theo JVMS `4.4.10`:

```text
CONSTANT_Dynamic_info {
    u1 tag;                         // 17
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}
```

Kích thước của entry này trong pool là **5 byte**, chưa tính các entry được trỏ đến.

| Field | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `tag` | Phân biệt loại entry | `17` = `CONSTANT_Dynamic` |
| `bootstrap_method_attr_index` | **Chỉ số 0-based** vào array `bootstrap_methods[]` của attribute `BootstrapMethods` trên class file này | `0` nghĩa là BSM entry đầu tiên |
| `name_and_type_index` | **Index của constant pool**, trỏ tới `CONSTANT_NameAndType_info` | `18` trỏ `GREETING:Ljava/lang/String;` |

**Bẫy index quan trọng:** constant pool dùng index như `#19`, thường bắt đầu từ 1; bootstrap table dùng **zero-based index** như `0`. Khi `javap` in:

```text
#19 = Dynamic #0:#18 // #0:GREETING:Ljava/lang/String;
```

thì:

- `#19`: vị trí **dynamic entry** trong constant pool.
- `#0`: vị trí BSM entry thứ **nhất** trong array `BootstrapMethods.bootstrap_methods[]`.
- `#18`: vị trí `NameAndType` trong constant pool.
- `GREETING`: tên logic của dynamic constant, **không phải tên method bootstrap**.
- `Ljava/lang/String;`: **field descriptor** xác định kiểu kết quả cần nhận.

### `name_and_type_index` dẫn đến field descriptor, không phải method descriptor

Một dynamic constant có tên và **field descriptor**:

```text
#16 = Utf8       GREETING
#17 = Utf8       Ljava/lang/String;
#18 = NameAndType #16:#17  // GREETING:Ljava/lang/String;
#19 = Dynamic     #0:#18
```

Một `CONSTANT_InvokeDynamic` dùng cùng cấu trúc 5 byte nhưng `NameAndType` phải chứa **method descriptor**, ví dụ `(Ljava/lang/String;)I`. Descriptor đó mô tả signature của call site, **không** mô tả kiểu trả về của một constant.

| Descriptor | Dạng | Dùng đúng cho |
| --- | --- | --- |
| `Ljava/lang/String;` | Field descriptor | Condy trả `String` |
| `I` | Field descriptor | Condy trả `int` |
| `J` | Field descriptor | Condy trả `long` |
| `[B` | Field descriptor | Condy trả `byte[]` |
| `()Ljava/lang/String;` | Method descriptor | Java method hoặc invokedynamic call site |
| `(II)I` | Method descriptor | Java method hoặc invokedynamic call site |
| `V` | `void` chỉ dùng làm return type của method | **Không phải** field descriptor của condy |

Condy có thể có **reference value bằng `null`** khi descriptor là reference type; không được nhầm `null` với “không có kết quả bootstrap”. Với primitive descriptor, bootstrap phải tạo một giá trị chuyển được về primitive cần thiết; `null` không phù hợp.

### Không ghi code bootstrap trong entry `Dynamic`

`CONSTANT_Dynamic_info` chỉ chứa **index/metadata**. Thân code Java của bootstrap method nằm ở một class/method khác, có thể là library trong JDK hoặc custom application code. Kết nối giữa dynamic entry và code được làm thông qua một **`CONSTANT_MethodHandle`** tại `BootstrapMethods`.

## 4. `BootstrapMethods`: attribute cấp class file, không phải method body

Theo JVMS `4.7.23`:

```text
BootstrapMethods_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 num_bootstrap_methods;
    {
        u2 bootstrap_method_ref;
        u2 num_bootstrap_arguments;
        u2 bootstrap_arguments[num_bootstrap_arguments];
    } bootstrap_methods[num_bootstrap_methods];
}
```

### Ý nghĩa từng field

| Field | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `attribute_name_index` | `u2` | Constant-pool index của `CONSTANT_Utf8("BootstrapMethods")` |
| `attribute_length` | `u4` | Số bytes **payload của attribute**, không tính 6 byte header |
| `num_bootstrap_methods` | `u2` | Số entry trong BSM array |
| `bootstrap_method_ref` | `u2` | Constant-pool index **phải** trỏ tới `CONSTANT_MethodHandle` |
| `num_bootstrap_arguments` | `u2` | Số static arguments của BSM entry |
| `bootstrap_arguments[]` | Mảng các `u2` | Mỗi phần tử là constant-pool index trỏ tới một **loadable constant** |

Trong `BootstrapMethods` có thể có **nhiều bootstrap specifiers**, và nhiều dynamic constants hoặc invokedynamic entries có thể cùng trỏ đến **một** BSM specifier. Một dynamic constant không cần bản sao method handle riêng nếu class-file builder đã deduplicate các entry hợp lệ.

### Điều kiện số lượng attribute

Nếu constant pool chứa **ít nhất một `CONSTANT_Dynamic` hoặc `CONSTANT_InvokeDynamic`**, class file phải có **đúng một** `BootstrapMethods` attribute. JVMS cũng quy định một class file có **tối đa một** attribute mang tên đó.

**Không** tạo một attribute `BootstrapMethods` riêng cho từng condy hoặc từng `invokedynamic`: nhiều BSM entries nằm trong **một attribute**.

### Tính kích thước: ví dụ có một BSM, hai static arguments

```text
num_bootstrap_methods = 1           // 2 byte
  bootstrap_method_ref = #15        // 2 byte
  num_bootstrap_arguments = 2       // 2 byte
  bootstrap_arguments[0] = #21      // 2 byte
  bootstrap_arguments[1] = #22      // 2 byte

attribute_length = 2 + (2+2+2*2) = 10 bytes
total attribute bytes = 6-byte header + 10-byte payload = 16 bytes
```

**Lưu ý:** `attribute_length=10` ở ví dụ không phải kích thước của toàn bộ class file, không bao gồm UTF8 metadata hoặc method code mà constant-pool references trỏ tới.

## 5. Sơ đồ tham chiếu chéo: Constant pool → BootstrapMethods → MethodHandle

Một class file thực tế có các entry sau:

```text
Constant pool
 ├─ #1  Utf8                 GeneratedCondy
 ├─ #2  Class                #1
 ├─ #8  Utf8                 BootstrapMethods
 ├─ #9  Utf8                 CondyClassfileDemo$Bootstrap
 ├─ #10 Class                #9
 ├─ #11 Utf8                 make
 ├─ #12 Utf8                 (Lookup;String;Class;String;int)String  (*)
 ├─ #13 NameAndType          #11:#12
 ├─ #14 Methodref            #10.#13
 ├─ #15 MethodHandle         6:#14  // REF_invokeStatic
 ├─ #16 Utf8                 GREETING
 ├─ #17 Utf8                 Ljava/lang/String;
 ├─ #18 NameAndType          #16:#17
 ├─ #19 Dynamic              #0:#18
 ├─ #20 Utf8                 item-
 ├─ #21 String               #20
 └─ #22 Integer              17

ClassFile.attributes
 └─ BootstrapMethods
      └─ bootstrap_methods[0]
           bootstrap_method_ref = #15
           bootstrap_arguments  = [#21, #22]

Code của GeneratedCondy.value()
 └─ ldc #19
     └─ resolve Dynamic #19
         └─ bootstrap_methods[0]
             └─ MethodHandle #15 → Methodref #14 → make(...)
```

`(*)` Chữ ký MethodHandle viết ngắn trong sơ đồ; trong constant pool thực là **method descriptor JVM đầy đủ**:

```text
(Ljava/lang/invoke/MethodHandles$Lookup;
 Ljava/lang/String;
 Ljava/lang/Class;
 Ljava/lang/String;
 I)Ljava/lang/String;
```

Khi ghi vào UTF8 constant-pool entry, các thành phần đứng **liền nhau**, không có dấu cách hay xuống dòng:

```text
(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/Class;Ljava/lang/String;I)Ljava/lang/String;
```

Có hai loại index trong sơ đồ mà cần đọc đúng:

- `Dynamic #19` trỏ bootstrap **entry 0**, không trỏ trực tiếp tới method `#0` trong constant pool.
- `BootstrapMethods.bootstrap_method_ref=#15` trỏ constant pool entry **MethodHandle**, không trỏ trực tiếp tới `Methodref #14` (mặc dù `MethodHandle #15` chứa reference tới `#14`).

### `REF_invokeStatic` nghĩa là gì?

`CONSTANT_MethodHandle_info` gồm `reference_kind` và `reference_index`. Giá trị `reference_kind=6` tương ứng `REF_invokeStatic`, nghĩa là handle tham chiếu phương thức static phù hợp. Với một bootstrap class bình thường:

```java
public static String make(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        String prefix,
        int number) {
    return prefix + name + ":" + number;
}
```

JVM resolve method handle và invoke nó trong quá trình resolve constant. Không được giả định mọi method handle trong mọi `BootstrapMethods` entry phải là static Java method: MethodHandle có nhiều reference kinds theo JVMS; **ví dụ này** dùng `REF_invokeStatic` cho rõ ràng.

## 6. Luồng resolution của JVM: bootstrap nhận được những gì?

Theo JVMS `5.4.3.6`, JVM cần resolve các symbolic references phục vụ bootstrap, tập hợp arguments, gọi bootstrap method handle, rồi kiểm tra kết quả.

Với **dynamic constant**, danh sách arguments thông thường được hiểu như:

```text
bootstrap(
    MethodHandles.Lookup lookup,  // Context của class đang chứa constant
    String name,                  // Tên ở NameAndType của condy
    Class<?> type,                // Kiểu từ field descriptor của condy
    ...staticArguments           // Các giá trị từ BootstrapMethods entry
)
```

Trong ví dụ:

```text
lookup.lookupClass() = GeneratedCondy.class
name                 = "GREETING"
type                 = String.class
static argument 1    = "item-"
static argument 2    = 17 (int)
```

JVM gọi bootstrap **theo ngữ nghĩa tương đương `MethodHandle.invokeWithArguments`** với bộ arguments. Method handle cần chấp nhận những arguments đó hoặc resolution có thể thất bại. Trong example, chữ ký bootstrap trùng chính xác:

```java
public static String make(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        String prefix,
        int number)
```

### Ý nghĩa của `Lookup`

`lookup` mang context của **class chứa dynamic constant**, không phải default context toàn JVM. Một số bootstrap functions hợp lệ có thể tra cứu symbol/private members phù hợp với quyền của caller.

**Không xem `Lookup` là quyền lực vô điều kiện.** Nó phải tôn trọng module/package/access rules, security boundaries và method handle resolution. Bootstrap muốn dùng member riêng tư ở nơi khác vẫn phải có quyền truy cập theo Java/JPMS.

### Dynamic constant có thể dùng static arguments nào?

Mỗi `bootstrap_arguments[]` là **index tới một loadable constant** của constant pool. Trong Java 11, ví dụ phổ biến:

- `CONSTANT_String`, `Integer`, `Long`, `Float`, `Double`;
- `CONSTANT_Class`, `CONSTANT_MethodType`, `CONSTANT_MethodHandle`;
- **`CONSTANT_Dynamic` khác**: cho phép static argument được tính động trước, tạo các **nested condy**.

Không thể đơn giản đặt một `CONSTANT_Fieldref` tùy ý trong mảng bootstrap arguments rồi cho rằng đó là giá trị đã load; JVM yêu cầu entry thuộc nhóm loadable theo JVMS.

Đối với numeric constant, giá trị được boxing phù hợp khi truyền vào array arguments dạng `Object[]` của bootstrap invocation. Số `17` từ `CONSTANT_Integer` trong ví dụ được adapt vào tham số `int number` của Java bootstrap method.

## 7. Lazy resolution, cache và các trường hợp chạy đồng thời

### 7.1. “Dynamic” không có nghĩa chạy lại mỗi lần đọc

Khi một constant được resolve thành công, kết quả resolution **được liên kết với symbolic reference của constant-pool entry**. Những lần `ldc` tiếp theo dùng kết quả đó, không cần gọi lại bootstrap như gọi một function trong mỗi vòng lặp.

```text
Tạo/load class GeneratedCondy
  └─ chưa cần resolve #19

Lần đầu thực hiện ldc #19
  ├─ resolve BSM và các static args
  ├─ gọi make(...) → "item-GREETING:17"
  └─ cài giá trị resolution cho #19

Lần tiếp theo thực hiện ldc #19
  └─ lấy giá trị đã resolve
```

Đây là **cache theo runtime constant-pool entry trong ngữ cảnh class liên quan**, không phải cache toàn tiến trình chỉ dựa trên tên chuỗi. Hai classes khác nhau có thể khai báo hai dynamic entries cùng tên, nhưng đó là hai symbolic references khác nhau.

**Không nhầm:** `ldc #19` không phải lời gọi `make()` mỗi lần chạy. Nó là thao tác **load một constant qua symbolic reference** đã được resolve hoặc cần resolve lần đầu.

### 7.2. Cạnh tranh resolution giữa nhiều threads

JVMS cho phép nhiều threads **đồng thời** cố resolve cùng symbolic reference; bootstrap method handle **có thể được gọi nhiều lần** khi race xảy ra. JVM chọn kết quả **một** lần invocation làm kết quả resolution hiển thị chung; kết quả invocation cạnh tranh còn lại có thể bị bỏ qua.

Vì vậy **không nên khẳng định bootstrap tuyệt đối chạy đúng một lần trên mọi JVM/luồng**. Ví dụ đơn luồng ở phần dưới cho `bootstrapCalls=1`, nhưng bootstrap trong sản phẩm thật nên:

- tránh side effects không thể lặp (tăng tiền, gửi email, ghi DB không idempotent);
- an toàn khi concurrency xảy ra;
- trả kết quả có ngữ nghĩa ổn định;
- không phụ thuộc vào thứ tự thread thực hiện bootstrap;
- tránh giữ references/secret quá thời gian cần thiết.

### 7.3. Thời điểm resolution và class initialization là những cơ chế khác nhau

`Class.forName`, `ClassLoader.loadClass`, `MethodHandles.Lookup.defineClass`, `<clinit>` và `ldc` liên quan loading/linking/initialization theo các quy tắc khác nhau.

**Không** viết tài liệu hoặc test dựa trên mệnh đề “vừa đọc class file có `Dynamic` là BSM chắc chắn chạy”. Trong chương trình ở phần 10, việc define class và lấy `Method` chưa khiến BSM chạy; lần gọi method có `ldc` mới khiến constant được resolve trong thử nghiệm.

Tương tự, **lỗi bootstrap** không nhất thiết là `ExceptionInInitializerError` từ một Java static initializer. Nó thuộc **resolution** của constant-pool symbolic reference, dù nó có thể xảy ra trong quá trình thực thi `<clinit>` nếu bytecode ở đó dùng condy.

## 8. Code instruction: `ldc`, `ldc_w` và `ldc2_w`

JVM không cần một opcode mới tên `condy`. Các lệnh load constant đã được mở rộng để hỗ trợ `CONSTANT_Dynamic`:

| Bytecode instruction | Khi dùng cho dynamic constant |
| --- | --- |
| `ldc index` | Load constant có kiểu chiếm một operand-stack slot từ CP index 8-bit |
| `ldc_w indexbyte1 indexbyte2` | Tương tự `ldc` nhưng CP index 16-bit |
| `ldc2_w indexbyte1 indexbyte2` | Load constant `long` hoặc `double` chiếm hai slots, kể cả dynamic descriptor `J` hoặc `D` |

Ví dụ:

```text
0: ldc #19 // Dynamic #0:GREETING:Ljava/lang/String;
2: areturn
```

`ldc #19` nằm ở bytecode của method `value()`. JVM biết constant có kiểu `String` từ descriptor `Ljava/lang/String;`, và kiểm tra kết quả bootstrap phải tương thích với kiểu đó.

Đối với một dynamic constant có descriptor `J`, phải dùng `ldc2_w`; không dùng `ldc` cho `long` rồi chờ verifier tự sửa. Với `int` (`I`) hoặc reference type, dùng `ldc`/`ldc_w` thích hợp.

### Vì sao class file cần biết kiểu trước khi bootstrap chạy?

Verifier phải kiểm tra **operand stack types** của method. Nếu `ldc` được khai báo đẩy một `String`, phần code sau đó có thể dùng `areturn` để trả `String`. Trước khi runtime gọi bootstrap, verifier đã có **type descriptor** của symbolic constant để kiểm tra bytecode. Nếu bootstrap thực tế trả một object không chuyển được về `String`, resolution thất bại; JVM không âm thầm đổi verified bytecode signature thành kiểu mới.

## 9. `CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic`: đừng nhầm tag 17 với 18

Hai cấu trúc có hình dạng:

```text
CONSTANT_Dynamic_info {
    u1 tag;                         // 17
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}

CONSTANT_InvokeDynamic_info {
    u1 tag;                         // 18
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}
```

Nhưng khác nhau ở **kết quả**:

| Đặc tính | Dynamic constant — tag 17 | Invokedynamic call site — tag 18 |
| --- | --- | --- |
| Ý nghĩa | Tính một **giá trị** | Liên kết một **CallSite** |
| `NameAndType` descriptor | **Field descriptor** `Ljava/lang/String;`, `I`, `J`... | **Method descriptor** `(I)Ljava/lang/String;`... |
| Bootstrap context argument thứ ba | `Class<?>` kiểu value mong đợi | `MethodType` mô tả call site |
| Kết quả cần trả | Giá trị chuyển được về dynamic field type | `CallSite` phù hợp method type |
| Bytecode chủ đạo | `ldc` / `ldc_w` / `ldc2_w` | `invokedynamic` |
| Dùng cùng `BootstrapMethods` attribute? | Có | Có |

Cú pháp `invokedynamic` cũng có thể thấy trong bytecode từ lambdas hoặc string concatenation của Java compiler. **Sự xuất hiện của `BootstrapMethods` trong `javap -v` chưa đủ để kết luận class đó có condy.** Phải kiểm tra constant pool có entry `Dynamic` tag 17 hay chỉ có `InvokeDynamic` tag 18.

Ngược lại, nếu `javap -v` thấy `Dynamic #0:NAME:Ljava/lang/String;`, hãy tìm đúng entry `BootstrapMethods[0]` và method bytecode/static arguments liên quan, không chỉ nhìn tên `BootstrapMethods` ở cuối output.

## 10. Chương trình Java 11 đầy đủ: tự tạo class file có `CONSTANT_Dynamic` thật

Java 11 **hỗ trợ condy ở JVM và class-file format**, nhưng **Java source không có cú pháp trực tiếp kiểu `condy x = ...`**. `javac --release 11` không bắt buộc sinh `CONSTANT_Dynamic` chỉ vì source khai báo `static final` hoặc string literal.

Vì vậy, để test đúng **đường chạy `ldc → Dynamic → BootstrapMethods`** mà không cần thư viện ngoài, chương trình dưới đây dùng `DataOutputStream` viết một class file tối giản có:

- class-file **major 55**, compatible Java 11;
- constant pool entries `#1..#22`, gồm `#19 = CONSTANT_Dynamic`;
- `bootstrap_method_attr_index=0`, `name_and_type_index=18`;
- `BootstrapMethods` có một entry, `MethodHandle #15`, hai static arguments `#21 = "item-"` và `#22 = 17`;
- một method `public static String value()` có bytecode `ldc #19; areturn`;
- bootstrap method static Java trong class `CondyClassfileDemo.Bootstrap`;
- một class thứ hai có cùng cấu trúc nhưng tên constant `BROKEN` để minh họa lỗi bootstrap được cache.

Mọi byte giá trị metadata được giải thích trong code. Đây là **class-file fixture dùng để học**, không phải bytecode generator cho production: thực tế nên dùng compiler/ASM/bytecode library có hỗ trợ condy và kiểm tra JVMS constraints.

### Nguồn chạy đầy đủ: `CondyClassfileDemo.java`

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.concurrent.atomic.AtomicInteger;

public final class CondyClassfileDemo {
    public static final class Bootstrap {
        static final AtomicInteger SUCCESS_CALLS = new AtomicInteger();
        static final AtomicInteger FAILURE_CALLS = new AtomicInteger();

        public static String make(MethodHandles.Lookup lookup, String name,
                                  Class<?> type, String prefix, int number) {
            if (!lookup.lookupClass().getName().startsWith("Generated")
                    || type != String.class) {
                throw new IllegalArgumentException(
                        "Unexpected lookup or type");
            }
            if ("BROKEN".equals(name)) {
                FAILURE_CALLS.incrementAndGet();
                throw new IllegalStateException("bootstrap refused");
            }
            SUCCESS_CALLS.incrementAndGet();
            return prefix + name + ":" + number;
        }
    }

    private static void utf(DataOutputStream out, String value)
            throws Exception {
        out.writeByte(1);      // CONSTANT_Utf8 tag
        out.writeUTF(value);   // Chỉ dùng ASCII trong fixture này
    }

    private static void cpClass(DataOutputStream out, int utfIndex)
            throws Exception {
        out.writeByte(7);      // CONSTANT_Class tag
        out.writeShort(utfIndex);
    }

    private static void nameType(
            DataOutputStream out, int name, int descriptor)
            throws Exception {
        out.writeByte(12);     // CONSTANT_NameAndType tag
        out.writeShort(name);
        out.writeShort(descriptor);
    }

    private static byte[] build(
            String className, String constantName) throws Exception {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);

        out.writeInt(0xCAFEBABE);
        out.writeShort(0);     // minor_version
        out.writeShort(55);    // major_version = Java 11
        out.writeShort(23);    // constant_pool_count: #1..#22

        utf(out, className);                        // #1
        cpClass(out, 1);                            // #2
        utf(out, "java/lang/Object");               // #3
        cpClass(out, 3);                            // #4
        utf(out, "value");                          // #5
        utf(out, "()Ljava/lang/String;");           // #6
        utf(out, "Code");                           // #7
        utf(out, "BootstrapMethods");               // #8
        utf(out, "CondyClassfileDemo$Bootstrap");    // #9
        cpClass(out, 9);                            // #10
        utf(out, "make");                           // #11
        utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/Class;"
                + "Ljava/lang/String;I)Ljava/lang/String;"); // #12
        nameType(out, 11, 12);                      // #13

        out.writeByte(10);                          // #14 Methodref
        out.writeShort(10);
        out.writeShort(13);

        out.writeByte(15);                          // #15 MethodHandle
        out.writeByte(6);                           // REF_invokeStatic
        out.writeShort(14);

        utf(out, constantName);                     // #16
        utf(out, "Ljava/lang/String;");             // #17
        nameType(out, 16, 17);                      // #18

        out.writeByte(17);                          // #19 Dynamic
        out.writeShort(0);                          // BSM entry 0
        out.writeShort(18);                         // NameAndType #18

        utf(out, "item-");                          // #20
        out.writeByte(8);                           // #21 String
        out.writeShort(20);

        out.writeByte(3);                           // #22 Integer
        out.writeInt(17);

        out.writeShort(0x0021); // class flags PUBLIC|SUPER
        out.writeShort(2);      // this_class
        out.writeShort(4);      // super_class
        out.writeShort(0);      // interfaces_count
        out.writeShort(0);      // fields_count

        out.writeShort(1);      // methods_count
        out.writeShort(0x0009); // method flags PUBLIC|STATIC
        out.writeShort(5);      // name: value
        out.writeShort(6);      // descriptor: ()Ljava/lang/String;
        out.writeShort(1);      // method attributes_count
        out.writeShort(7);      // "Code"
        out.writeInt(15);       // Code attribute_length
        out.writeShort(1);      // max_stack
        out.writeShort(0);      // max_locals
        out.writeInt(3);        // code_length
        out.writeByte(0x12);   // ldc
        out.writeByte(19);     // #19 Dynamic
        out.writeByte(0xB0);   // areturn
        out.writeShort(0);     // exception_table_length
        out.writeShort(0);     // Code attributes_count

        out.writeShort(1);     // class attributes_count
        out.writeShort(8);     // "BootstrapMethods"
        out.writeInt(10);      // attribute_length
        out.writeShort(1);     // num_bootstrap_methods
        out.writeShort(15);    // bootstrap_method_ref #15
        out.writeShort(2);     // num_bootstrap_arguments
        out.writeShort(21);    // "item-"
        out.writeShort(22);    // Integer 17

        out.flush();
        return buffer.toByteArray();
    }

    private static Method load(
            String className, String constantName) throws Exception {
        byte[] bytes = build(className, constantName);
        Files.write(Paths.get(className + ".class"), bytes);
        Class<?> defined = MethodHandles.lookup().defineClass(bytes);
        return defined.getMethod("value");
    }

    public static void main(String[] args) throws Exception {
        Method ok = load("GeneratedCondy", "GREETING");
        System.out.println(
                "afterDefineCalls=" + Bootstrap.SUCCESS_CALLS.get());
        System.out.println("first=" + ok.invoke(null));
        System.out.println("second=" + ok.invoke(null));
        System.out.println(
                "bootstrapCalls=" + Bootstrap.SUCCESS_CALLS.get());

        Method broken = load("GeneratedBroken", "BROKEN");
        for (int i = 1; i <= 2; i++) {
            try {
                broken.invoke(null);
                System.out.println("unexpectedSuccess=" + i);
            } catch (InvocationTargetException ex) {
                System.out.println("failure" + i + "=" +
                        ex.getCause().getClass().getSimpleName());
            }
        }
        System.out.println("failedBootstrapCalls=" +
                Bootstrap.FAILURE_CALLS.get());
    }
}
```

**Biên dịch/chạy:**

```bash
javac --release 11 CondyClassfileDemo.java
java CondyClassfileDemo
```

Lưu ý: lần chạy tạo **`GeneratedCondy.class` và `GeneratedBroken.class` trong working directory** để tiện inspection. Hãy chạy trong một thư mục thực hành riêng, không đặt các file class tự tạo trong build output/JAR sản phẩm.

**Stdout đã kiểm chứng trên JDK có hỗ trợ class-file version 55:**

```text
afterDefineCalls=0
first=item-GREETING:17
second=item-GREETING:17
bootstrapCalls=1
failure1=BootstrapMethodError
failure2=BootstrapMethodError
failedBootstrapCalls=1
```

### Kết quả chứng minh điều gì?

1. `afterDefineCalls=0`: ở lần thử này, `Lookup.defineClass(bytes)` và reflection tìm method không tự khiến dynamic constant được resolve.
2. `first=item-GREETING:17`: khi method `value()` thực hiện `ldc #19`, JVM gọi `Bootstrap.make` với `name=GREETING`, `type=String.class` và hai static arguments. Bootstrap trả chuỗi đã dẫn xuất.
3. `second=item-GREETING:17`: lần gọi thứ hai nhận lại kết quả của cùng symbolic reference.
4. `bootstrapCalls=1`: trong **thử nghiệm tuần tự này**, bootstrap thành công chỉ thực thi một lần cho constant-pool entry ấy.
5. `failure1/2=BootstrapMethodError`: bootstrap của một dynamic constant khác cố tình ném `IllegalStateException`; JVMS xử lý như lỗi bootstrap resolution, qua reflection được quan sát thành `BootstrapMethodError`.
6. `failedBootstrapCalls=1`: lần thử lại cùng constant bị lỗi **không tự gọi lại bootstrap**, mà nhìn thấy failure đã được ghi nhận.
7. Hai generated classes là **hai class riêng** với các constant-pool entries riêng, dù cấu trúc nhị phân giống nhau. Cache resolution của một class không tự chuyển sang class kia.

**Không suy rộng** từ `bootstrapCalls=1` thành guarantee bootstrap luôn chạy đúng một lần trong môi trường đa luồng. Nếu nhiều threads cố resolve đồng thời một entry chưa resolve, JVMS cho phép nhiều invocations và chọn một kết quả.

### Tại sao bytecode vẫn hợp lệ dù generated class không có constructor?

Class fixture này chỉ cần một method **`public static String value()`**; nó không có mục tiêu tạo instance. Class file có thể được load và gọi method static dù không khai báo instance constructor `<init>`. Đây chỉ là thiết kế test tối giản; codegen production thường có các metadata/method khác.

### Vì sao `DataOutputStream.writeUTF` ở ví dụ vẫn dùng được?

Class-file `CONSTANT_Utf8` dùng **modified UTF-8**. `DataOutputStream.writeUTF` dùng modified UTF-8 với length prefix hai byte, phù hợp cho các chuỗi **ASCII ngắn** của fixture. Khi viết generator thực tế phải tuân theo giới hạn và encoding constant pool của JVMS, xử lý Unicode/length/duplicate indices đúng; tốt nhất dùng library classfile hiện đại thay vì sao chép emitter tối giản này.

## 11. Kiểm tra `javap -v`: nhìn đúng hai đầu tham chiếu

Sau khi chạy `java CondyClassfileDemo`:

```bash
javap -v GeneratedCondy.class
javap -c GeneratedCondy.class
javap -v GeneratedBroken.class
```

Trên PowerShell:

```powershell
javap -v GeneratedCondy.class
javap -v GeneratedBroken.class
```

**Một phần output `javap -v` đã kiểm chứng:**

```text
major version: 55
...
#15 = MethodHandle       6:#14   // REF_invokeStatic CondyClassfileDemo$Bootstrap.make:...
#19 = Dynamic            #0:#18  // #0:GREETING:Ljava/lang/String;
#21 = String             #20     // item-
#22 = Integer            17
...
0: ldc #19                        // Dynamic #0:GREETING:Ljava/lang/String;
...
BootstrapMethods:
  0: #15 REF_invokeStatic CondyClassfileDemo$Bootstrap.make:...
    Method arguments:
      #21 item-
      #22 17
```

Dấu `...` trong đoạn trích biểu thị **những dòng `javap` đã lược bớt để tập trung vào thông tin quan trọng**, không phải stdout đầy đủ của tool. Lệnh `java` mới là nguồn stdout đầy đủ của chương trình ở phần trên. Một số bản `javap` in nhãn `Method arguments:` hoặc format dòng khác nhau, nhưng các indices và quan hệ cơ bản vẫn là một.

### Cách lần ngược

1. Tại `ldc #19`, tìm `constant_pool[#19]`.
2. Đọc `#19 = Dynamic #0:#18`.
3. Lần `#18 = NameAndType` để biết tên `GREETING` và descriptor `Ljava/lang/String;`.
4. Lấy **bootstrap entry 0** trong `BootstrapMethods` ở cuối `javap -v`.
5. Đi đến `bootstrap_method_ref #15`, rồi `#15 MethodHandle 6:#14`.
6. Theo `#14 Methodref` để xác định class/method và JVM descriptor của bootstrap.
7. Đọc danh sách static arguments `#21`, `#22`.
8. So với thực thi: `Lookup, String, Class, "item-", 17` → String kết quả.

**Không lẫn `#0` ở dòng `Dynamic #0:#18` với constant-pool index 0**, vì `#0` ở đây là **BootstrapMethods table index**.

## 12. Bootstrap helpers có sẵn trong Java 11: `ConstantBootstraps`

JDK 11 đưa vào `java.lang.invoke.ConstantBootstraps` — tập các static bootstrap methods hữu ích cho dynamic constants, ví dụ:

| Method | Công dụng |
| --- | --- |
| `nullConstant(Lookup, String, Class<?>)` | Trả `null` cho reference type phù hợp |
| `primitiveClass(Lookup, String, Class<?>)` | Lấy `Class` tương ứng một primitive descriptor |
| `enumConstant(Lookup, String, Class<E>)` | Tìm enum constant theo tên/kiểu |
| `getStaticFinal(...)` | Lấy giá trị static final field theo quy tắc API |
| `invoke(...)` | Gọi một MethodHandle và trả kết quả |
| `fieldVarHandle(...)` | Tạo VarHandle cho instance field |
| `staticFieldVarHandle(...)` | Tạo VarHandle cho static field |
| `arrayVarHandle(...)` | Tạo VarHandle cho array component access |

Các method này có thể được chỉ định làm bootstrap trong `BootstrapMethods` nếu signature và static arguments tương thích. Ví dụ, `enumConstant` nhận `name` và `type` từ condy để tìm một enum value hợp lệ.

**Gọi Java method trực tiếp**:

```java
Object value = ConstantBootstraps.nullConstant(
        MethodHandles.lookup(), "unused", String.class);
System.out.println(value == null); // true
```

là demo API helper, **không phải** demo JVM resolve một `CONSTANT_Dynamic`. Để thực sự có condy, constant pool phải chứa tag 17 và đúng bootstrap link; phần 10 đã tạo một ví dụ thực.

Không giả định mọi thành viên của `ConstantBootstraps` không kiểm tra quyền hoặc có thể đọc arbitrary private members: `Lookup` và algorithm-specific constraints vẫn được áp dụng. Khi `getStaticFinal` được dùng, class initialization/field access policy có thể là một phần của hành vi, không được coi là “read raw bytes” trong constant pool.

## 13. Nested condy: static argument có thể là một dynamic constant khác

Một `BootstrapMethods.bootstrap_arguments[]` có thể tham chiếu đến `CONSTANT_Dynamic` khác, ví dụ:

```text
Dynamic #30 = OUTER (descriptor: String)
  bootstrap[2] static args:
    #29 = Dynamic INNER (descriptor: String)

JVM resolve OUTER:
  resolve static arg #29 (INNER) trước
  invoke bootstrap của OUTER với giá trị INNER đã resolve
```

Cơ chế này cho phép tạo cấu trúc constants phức tạp từ những giá trị động trung gian. Tuy nhiên:

- Không suy ra mọi nested constant đều có thứ tự resolution tùy ý: JVMS quy định việc resolve static arguments theo thứ tự được ghi.
- Nếu một `CONSTANT_Dynamic` tham chiếu **chính nó** (trực tiếp hoặc gián tiếp) trong chuỗi static arguments, JVMS không cho phép resolution hoàn tất bình thường.
- Với chu kỳ đó, JVMS Java 11 chỉ định **`StackOverflowError`** tại điểm cần resolve lại reference đang trong chu trình. Không tùy tiện ghi mọi cycle đều luôn là `BootstrapMethodError`.
- Một chu kỳ phát sinh do bootstrap code tự đọc lại constant đang resolve cũng có thể tạo recursive calls và stack overflow.

**Không xem condy như dependency injection container** với cycle detection tự động, rollback hoặc caching across application scopes. Nó là một cơ chế JVM linkage có các quy tắc cụ thể và phải được dùng thận trọng.

## 14. Error và type checking: tại sao bootstrap thành công chạy code chưa chắc constant hợp lệ?

### 14.1. Bootstrap trả sai kiểu

Giả sử dynamic entry khai báo `Ljava/lang/String;` nhưng bootstrap trả `Integer.valueOf(7)`. JVM phải kiểm tra/conversion kết quả sang kiểu đã khai báo. Nếu conversion thất bại bằng `ClassCastException` hoặc `NullPointerException`, resolution thất bại bằng `BootstrapMethodError` theo JVMS.

```text
CONSTANT_Dynamic:
   name="MESSAGE"
   descriptor="Ljava/lang/String;"

Bootstrap returns Integer(7)
   ↓
Cannot convert result to String
   ↓
BootstrapMethodError
```

Với primitive descriptor `J`, bootstrap phải trả giá trị chuyển được về `long` theo quy tắc method-handle conversion, không thể trả `null`.

Với reference descriptor, bootstrap có thể trả `null` nếu contract của giá trị chấp nhận null. Ví dụ `ConstantBootstraps.nullConstant` được thiết kế cho trường hợp ấy.

### 14.2. Bootstrap ném exception

Nếu bootstrap ném **một exception không phải subclass của `Error`**, JVMS bọc nó vào `BootstrapMethodError`. Nếu bootstrap invocation ném một `Error`, JVMS có thể để chính `Error` đó báo lỗi resolution theo quy tắc. Lỗi xảy ra trước khi invoke bootstrap (method handle resolution, static argument resolution, loading constraint...) có thể hiện dưới các dạng linkage errors khác.

Ví dụ đầy đủ ở phần 10:

```text
Bootstrap.make(..., name="BROKEN", ...)
    throws IllegalStateException
         ↓
    BootstrapMethodError khi resolve Dynamic
```

Không phải mọi lỗi condy đều do “Java compiler bug”; rất nhiều lỗi đến từ method handle/static arguments/type descriptor hoặc classpath bị lệch phiên bản.

### 14.3. Lỗi được cache

Theo JVMS, một symbolic reference resolve thất bại vẫn ghi nhận failure cho những lần resolve kế tiếp; với dynamic constant, bootstrap **không tự chạy lại để thử cứu** cùng entry đó.

Vì vậy, nếu bootstrap phụ thuộc dữ liệu ngoài không sẵn ở lần đầu, một lúc sau mới có dữ liệu rồi gọi `ldc` lần nữa có thể vẫn nhận cùng lỗi. **Không dùng condy để lấy cấu hình biến đổi liên tục, token hết hạn hoặc giá cả realtime** nếu muốn cập nhật linh hoạt; giá trị hay lỗi đã liên kết với entry phải được xem là một kết quả resolution.

### 14.4. Có thể gặp những lỗi khác

| Lỗi | Tình huống điển hình | Hướng kiểm tra |
| --- | --- | --- |
| `ClassFormatError` | Class-file bytes/constant pool/attribute cấu trúc sai | Kiểm tra `major_version`, tags, count, lengths, indices |
| `UnsupportedClassVersionError` | Runtime quá cũ không hiểu major 55 của class file | Chạy trên JDK 11+, không load class file Java 11 vào Java 8 |
| `VerifyError` | Opcode và descriptor/operand-stack types không khớp | Kiểm tra `ldc` vs `ldc2_w`, verifier types, method `Code` |
| `NoSuchMethodError` / `IllegalAccessError` | Bootstrap method ref không còn tồn tại/không được truy cập | So sánh CP Methodref, method descriptor, module/class loader |
| `BootstrapMethodError` | Bootstrap exception, return type conversion không hợp lệ... | Kiểm tra cause, method handle, argument list và expected type |
| `StackOverflowError` | Cycle khi condy resolve chính mình theo JVMS `5.4.3.6` | Phân tích static argument dependency graph |
| `LinkageError` khác | Lỗi resolve một symbolic reference phụ thuộc | Kiểm tra runtime artifacts/version/provider |

**Đừng bắt `Throwable` rồi nuốt lỗi để tiếp tục chạy với một “default constant” mù quáng.** Với class file bị lỗi linkage, nên fail rõ ràng và báo nguyên nhân có thể xử lý được.

## 15. Chi phí, concurrency và an toàn khi dùng condy

### 15.1. Bootstrap code được thực thi trong quá trình linkage

Bootstrap method không chỉ là metadata vô hại. Nó là **mã Java có thể thực thi** trong ngữ cảnh resolution. Nếu một class file do nguồn không tin cậy cung cấp, việc load/execute nó có thể dẫn đến tác dụng phụ của bootstrap. Không coi một JAR là “chỉ chứa data constant” khi nó có method handles/binary code có khả năng chạy.

Giữ bootstrap methods:

- deterministic và side-effect-free khi có thể;
- không truy cập network/database không cần thiết;
- tránh blocking lâu khiến thread đầu tiên đòi constant bị treo;
- có kiểm tra input/name/type và access scope;
- không lưu secrets/token trong static args hoặc output logs;
- an toàn khi nhiều threads cùng gọi trong lần resolution đầu;
- không dùng một cache process-global tự tạo khi constant cần được cô lập theo class loader/module.

### 15.2. Giá trị object có thể mutable

`CONSTANT_Dynamic` là “constant” theo nghĩa **result of resolution được tái sử dụng**, không có nghĩa một object được trả về là **immutable**.

Nếu bootstrap trả một mutable object, các lần load cùng entry có thể nhận **cùng reference** đến object đó; việc mutate state có thể ảnh hưởng những nơi sử dụng khác. Nếu application cần constant an toàn để chia sẻ, nên trả object immutable/value type phù hợp hoặc bảo đảm API không làm lộ mutable state.

### 15.3. Cache theo symbolic reference không phải theo tên

Hai entries cùng tên/descriptor nhưng ở **hai class files** khác nhau không bắt buộc chia sẻ resolution value. Class loader và runtime class identity cũng đóng vai trò quan trọng. Vì vậy không đặt giả định “bất kỳ `GREETING` nào trên JVM đều chỉ bootstrap một lần”.

### 15.4. Tương thích công cụ

Các bytecode tools, obfuscators, shrinkers, shading và instrumentation agents phải:

- hiểu class-file major version phù hợp;
- bảo toàn `CONSTANT_Dynamic` tag 17;
- bảo toàn hoặc cập nhật đúng `BootstrapMethods` và CP indexes;
- giữ nguyên các method handles/BSM descriptors sau rename/repackage;
- không xóa một BSM entry đang được dynamic hoặc invokedynamic tham chiếu;
- không tạo cycles/indices vượt phạm vi khi sửa CP.

Với ASM, dùng phiên bản có hỗ trợ **`ConstantDynamic`** và Java 11 bytecode trở lên; không áp dụng tutorial ASM cũ chỉ hiểu `invokedynamic`. Trên các JDK hiện đại có thêm class-file APIs dành cho version mới hơn, nhưng **không dùng API không tồn tại trong Java 11** nếu mục tiêu là `javac --release 11`.

## 16. Khi nào condy có ích, khi nào dùng field/source code bình thường?

| Nhu cầu | Cơ chế thường phù hợp | Lý do |
| --- | --- | --- |
| Chuỗi hoặc số literal đã biết tại compile time | Java literal/source `static final` theo yêu cầu | Dễ hiểu, compiler xử lý trực tiếp |
| Một object bất biến cần tính theo class-level linkage và dùng lại | `CONSTANT_Dynamic` qua compiler/bytecode generator phù hợp | JVM quản lý resolution/caching |
| Lời gọi cần liên kết động một lần thành call site | `invokedynamic` | BSM trả `CallSite`, không phải value constant |
| Cấu hình thay đổi trong thời gian chạy | Config service, field/holder có lifecycle rõ | Condy result đã resolve không tự refresh |
| Credential/token có thời hạn | Secret/token provider | Không nên nhúng vào CP static args hoặc cache như constant bất biến |
| Lambda/interoperability với dynamic language | Compiler/runtime framework phù hợp | Không cần tự ghi CP nhị phân bằng tay |
| Debug class-file instrumentation | `javap -v` + classfile-aware tool | Quan sát đúng metadata/call site |
| Tạo class file arbitrary cho sản phẩm | Bytecode generator được bảo trì và test | Tránh sai `constant_pool_count`, length, indices, verifier |

Trong hầu hết ứng dụng Java bình thường, bạn **không phải tự viết `CONSTANT_Dynamic`**. Nó phục vụ compiler, library và runtime tooling muốn biểu diễn những constants khó/không tiện mã hóa trực tiếp trong CP truyền thống. Kiến thức về nó đặc biệt hữu ích khi đọc `javap -v`, debug `BootstrapMethodError`, xây bytecode instrumentation hoặc tìm hiểu thiết kế JVM.

## 17. Quy trình đọc nhanh một class file có `BootstrapMethods`

Sử dụng:

```bash
javap -v -p ExampleClass
javap -c -p ExampleClass
```

Trong output:

1. Xác định `major version`: với condy cần class-file version hỗ trợ Java 11 (major 55+) và runtime đủ mới.
2. Tìm `Constant pool:`, xem có `Dynamic` (tag 17) hoặc `InvokeDynamic` (tag 18).
3. Với từng `Dynamic`, ghi **CP index**, **BSM index** và **NameAndType index**.
4. Lần `NameAndType` sang tên và **field descriptor**.
5. Đến `BootstrapMethods:`, tìm **đúng BSM index zero-based**.
6. Lần `bootstrap_method_ref` sang `MethodHandle` và `Methodref/InterfaceMethodref` liên quan.
7. Ghi rõ **static argument CP indexes** và kiểu dữ liệu từng giá trị.
8. Với code method, tìm `ldc`, `ldc_w` hoặc `ldc2_w` trỏ tới dynamic entry.
9. Nếu có lỗi runtime, so expected type với BSM result; tra nested dependencies, cycles và metadata sau repackage.
10. Ghi rõ class loader/module và đường dẫn JAR thực tế để tránh inspect sai artifact.

**Phân biệt hai cách nhìn:** `javap -v` giúp thấy **metadata class file**; `java` chạy code cho thấy **kết quả runtime**. `javap` không tự gọi bootstrap, nên nó không thể chứng minh bootstrap trả về đúng value chỉ bằng một dòng `Dynamic #...`.

## 18. Những hiểu lầm phổ biến

| Hiểu lầm | Giải thích đúng |
| --- | --- |
| `constant_pool` chỉ lưu giá trị literal | Có cả symbolic references và dynamic entries cần resolve |
| `CONSTANT_Dynamic` là một method được gọi mỗi lần `ldc` | Là một **value** được resolve rồi dùng lại |
| `CONSTANT_Dynamic` tag 18 | Sai; tag **17**, invokedynamic là **18** |
| `bootstrap_method_attr_index=0` là CP index 0 | Sai; đó là **BSM table index** |
| `NameAndType` của condy chứa method descriptor | Sai; chứa **field descriptor** |
| `BootstrapMethods` chỉ dùng cho `invokedynamic` | Sai; còn dùng cho `CONSTANT_Dynamic` |
| Mỗi dynamic constant có một `BootstrapMethods` attribute riêng | Sai; class file có **một attribute**, chứa bảng nhiều entries |
| `bootstrap_method_ref` trỏ ngay tới `Methodref` | Sai; nó trỏ tới **`MethodHandle`** CP entry |
| Static arguments là những biến Java truyền khi gọi `ldc` | Sai; chúng là các **loadable CP entries** được chỉ định trong attribute |
| Java source `static final` tự động nghĩa là condy | Sai; `javac` có thể dùng `ConstantValue`, `ldc` literal hoặc `<clinit>` |
| Java 11 có keyword `condy` | Không; condy là classfile/JVM mechanism |
| `ldc` load được `long` dynamic | Không; category-2 `J/D` dùng `ldc2_w` |
| Bootstrap phải trả `CallSite` | Chỉ đúng với **`invokedynamic`**; condy trả **value** phù hợp kiểu |
| Bootstrap của condy nhất định chạy đúng một lần | Trong race JVM có thể gọi nhiều lần, chọn một kết quả |
| Lỗi bootstrap lần đầu rồi lần hai sẽ thử lại | Failure resolution được ghi nhận; không tự retry BSM |
| Condy bắt buộc có Object reference không-null | Reference condy có thể nhận `null` khi type cho phép |
| Mọi cyclic condy đều là `BootstrapMethodError` | Theo JVMS `5.4.3.6`, vòng dependency khi resolution có `StackOverflowError` |
| Bootstrap sửa system property sẽ tự động refresh condy | Cache resolution không tự cập nhật với property ngoài |
| Thấy `BootstrapMethods` nghĩa là chắc chắn có condy | Có thể chỉ có `InvokeDynamic` từ lambda/string concat |
| `getDeclaredMethods()` của class giúp xem CP tags | Reflection không thay thế class-file parser |
| Một BSM dùng lại cho hai classes nghĩa là một cache chung | Resolution theo symbolic references của từng runtime class |
| `ConstantBootstraps.nullConstant(...)` gọi trực tiếp là test condy | Không; cần CP tag 17 và JVM linkage path |
| Condy vượt qua module/private access restrictions | `Lookup` và method handle access vẫn chịu rules JVM |
| Java 8 chạy được class file major 55 | Không; runtime không hỗ trợ version sẽ từ chối |

## 19. Câu hỏi tự kiểm tra (có đáp án)

**1.** `CONSTANT_Dynamic` có tag bằng bao nhiêu? Và Java version nào giới thiệu?

**Đáp án:** **17**, bổ sung theo JEP 309 ở **Java 11**, class-file major **55**.

**2.** `CONSTANT_Dynamic_info` có những field nào?

**Đáp án:** `u1 tag`, `u2 bootstrap_method_attr_index`, `u2 name_and_type_index` — tổng 5 byte.

**3.** `bootstrap_method_attr_index=0` trỏ đến đâu?

**Đáp án:** Entry đầu tiên trong `BootstrapMethods.bootstrap_methods[]` của **cùng ClassFile**, không phải CP index 0.

**4.** `name_and_type_index` của condy trỏ đến kiểu descriptor nào?

**Đáp án:** `CONSTANT_NameAndType` chứa **field descriptor** (ví dụ `Ljava/lang/String;`, `I`, `J`), không phải method descriptor.

**5.** `BootstrapMethods.bootstrap_method_ref` trỏ loại CP entry nào?

**Đáp án:** `CONSTANT_MethodHandle_info`. MethodHandle có reference kind và reference index tới method/field tương ứng.

**6.** Điều kiện tồn tại `BootstrapMethods` attribute là gì?

**Đáp án:** Class có ít nhất một `CONSTANT_Dynamic` hoặc `CONSTANT_InvokeDynamic` phải có **đúng một** `BootstrapMethods` attribute. Class file có tối đa một attribute loại đó.

**7.** Nếu attribute có một bootstrap method với hai static arguments, payload dài bao nhiêu byte?

**Đáp án:** `u2 count` (2) + `u2 method ref` (2) + `u2 args count` (2) + hai `u2` indices (4) = **10 byte**. Header sáu byte không tính trong `attribute_length`.

**8.** Hai static arguments `#21` và `#22` trong demo có giá trị gì?

**Đáp án:** `#21 = CONSTANT_String "item-"`, `#22 = CONSTANT_Integer 17`. Chúng là arguments thứ tư và thứ năm sau ba context arguments do JVM cấp.

**9.** JVM cung cấp ba arguments đầu nào cho condy bootstrap thông thường?

**Đáp án:** `MethodHandles.Lookup` cho caller context, `String` tên constant và `Class<?>` kiểu value đã khai báo.

**10.** Condy trả `String` nên dùng bytecode nào trong demo?

**Đáp án:** `ldc #19`; kết quả `String` được đặt lên stack rồi `areturn`. Nếu descriptor là `J`/`D` thì dùng `ldc2_w`.

**11.** Tại sao `afterDefineCalls=0` trong demo?

**Đáp án:** `Lookup.defineClass` đã định nghĩa class nhưng demo chưa thực hiện `ldc #19` để resolve constant. Đó là quan sát của lần chạy, không phải lý do để phụ thuộc vào eager/lazy class initialization ngoài contract.

**12.** `bootstrapCalls=1` có bảo đảm trên mọi runtime đa luồng không?

**Đáp án:** Không. Resolution đồng thời có thể gọi BSM nhiều lần; JVM cài kết quả một invocation vào symbolic reference chung.

**13.** Nếu bootstrap trả `Integer` nhưng condy descriptor là `Ljava/lang/String;` thì sao?

**Đáp án:** Kết quả không chuyển được về kiểu `String`; dynamic constant resolution thất bại, thường bằng `BootstrapMethodError` do `ClassCastException` theo JVMS.

**14.** Bootstrap ném `IllegalStateException`, lần gọi `ldc` tiếp theo có tự thử lại không?

**Đáp án:** Không. Lỗi resolution được ghi nhận; demo báo `BootstrapMethodError` hai lần nhưng `FAILURE_CALLS=1`.

**15.** Condy reference có thể nhận `null` không?

**Đáp án:** Có nếu descriptor là **reference type** và bootstrap trả null phù hợp; `ConstantBootstraps.nullConstant` minh họa. Với primitive type, null không hợp lệ.

**16.** `BootstrapMethods` có nghĩa class chắc chắn dùng `CONSTANT_Dynamic` không?

**Đáp án:** Không. Attribute cũng được dùng cho `CONSTANT_InvokeDynamic`. Phải xem CP entries và bytecode.

**17.** Nested condy có thể được dùng như một static argument không?

**Đáp án:** Có. JVM resolve các arguments theo thứ tự trước khi invoke BSM bên ngoài; cycle tham chiếu chính mình không được chấp nhận và có thể dẫn đến `StackOverflowError` như JVMS quy định.

**18.** Vì sao không nên dùng bootstrap để đọc access token hết hạn?

**Đáp án:** Kết quả/lỗi resolution được cache theo CP entry, không tự cập nhật khi token đổi; còn rủi ro lộ secret trong bytecode/log.

**19.** Khác biệt chính giữa `CONSTANT_Dynamic` và `CONSTANT_InvokeDynamic`?

**Đáp án:** Tag 17 tạo **một value** có field descriptor, load qua `ldc`; tag 18 tạo **CallSite** có method descriptor, dùng `invokedynamic`.

**20.** Làm sao biết class-file example thật sự dùng condy mà không chỉ gọi bootstrap Java method bình thường?

**Đáp án:** Dùng `javap -v` xác nhận `#19 = Dynamic #0:#18`, `BootstrapMethods[0]` trỏ `MethodHandle` và `value()` có `ldc #19`. Thử runtime cho thấy bootstrap chạy khi resolve, không phải do user code gọi `Bootstrap.make` trực tiếp.

## 20. Tài liệu chính thức, còn áp dụng

- [OpenJDK JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309): giới thiệu `CONSTANT_Dynamic` trong Java 11, mục tiêu mở rộng constant pool và bootstrap linkage.
- [Java SE 11 JVMS `4.1 — ClassFile](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.1): `ClassFile`, version, constant pool, attributes.
- [Java SE 11 JVMS `4.4.10 — CONSTANT_Dynamic/InvokeDynamic](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10): tag 17/18, `bootstrap_method_attr_index`, `name_and_type_index`.
- [Java SE 11 JVMS `4.7.23 — BootstrapMethods](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.23): binary attribute format, method handle, static arguments, multiplicity.
- [Java SE 11 JVMS `5.4.3.6 — Resolution](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6): BSM invocation, context args, conversion, caching, concurrent resolution và cycles.
- [Java SE 11 JVMS `6.5 — ldc/ldc_w/ldc2_w](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-6.html): instruction types, dynamic constant loading và category-two values.
- [Oracle Java SE 11 — ConstantBootstraps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): standard helpers cho dynamically-computed constants.
- [Oracle Java SE 11 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): caller context, `defineClass`, access rules.
- [Oracle Java SE 11 — MethodHandle](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandle.html): method-handle invocation và argument adaptation.
- [Java SE 26 JVMS `4.4.10 và `4.7.23](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html): xác nhận cơ chế condy và BootstrapMethods vẫn tồn tại trong JVM hiện hành; không phải công nghệ legacy.
- [Oracle Java SE 11 — javap](https://docs.oracle.com/en/java/javase/11/tools/javap.html): kiểm tra CP, attributes và method code với `-v`, `-c`, `-p`.

**Ghi nhớ:** `CONSTANT_Dynamic` **tag 17** không mang giá trị sẵn; nó giữ **BSM table index + NameAndType**. `BootstrapMethods` nằm ở **class-file attributes**, giữ **MethodHandle và static arguments**. JVM resolve chúng theo JVMS và cài giá trị/lỗi cho symbolic reference; `ldc` tiếp theo đọc kết quả đã liên kết. Tách rõ **constant pool index** khỏi **BootstrapMethods index**, **field descriptor** khỏi **method descriptor**, và **value bootstrap** của condy khỏi **CallSite bootstrap** của invokedynamic.