# 14.3 Phân giải bằng `ldc`, lưu giá trị đã chọn và xử lý lỗi phân giải

## 1. Mục tiêu: hiểu hằng động được “tính một lần” như thế nào

**Hằng động** (*dynamically computed constant*, thường viết **condy**) là một giá trị trong **run-time constant pool** của Java Virtual Machine (JVM), được xác định bằng cách chạy một **bootstrap method (BSM)** khi symbolic reference tới hằng cần được phân giải. Cơ chế này được biểu diễn bằng mục **`CONSTANT_Dynamic`** trong class file (hỗ trợ từ class-file version 55, Java 11).

Nó khác với hằng literal `"hello"` hay `42` được compiler ghi sẵn: một `CONSTANT_Dynamic` mô tả **cách tính hoặc lấy giá trị**, còn giá trị thực sự do bootstrap tạo ra trong quá trình resolution.

Trọng tâm của mục **14.3** gồm:

1. `ldc`, `ldc_w` và `ldc2_w` **đọc một hằng động ra sao**, và khi nào JVM cần gọi BSM.
2. Khi có nhiều bytecode instruction tham chiếu **cùng một `CONSTANT_Dynamic`**, JVM **lưu giá trị đã chọn** ở phạm vi nào; trạng thái Java bên ngoài thay đổi có khiến BSM chạy lại không?
3. JVM phản ứng thế nào nếu BSM ném exception, trả **không đúng kiểu** hoặc trả `null`; khác nhau giữa một hằng **reference** và một hằng **primitive**.
4. **Thử sử dụng lại sau lỗi resolution** có tự “retry” bootstrap không? Sử dụng class loader mới có thay đổi điều gì?
5. Phân biệt việc cache của **`CONSTANT_Dynamic`** với quy tắc liên kết theo **lexical instruction** của `invokedynamic`, tránh trộn hai cơ chế.

Bài này dùng **một chương trình Java 17+ tự tạo class file chứa `CONSTANT_Dynamic` thật**, kiểm thử bằng `javac`/`java`, và dùng `javap -v -c` để nhìn opcode `ldc`, `ldc_w`. Không cần cài thư viện bytecode ngoài.

> **Điểm quan trọng nhất:** Với một hằng động đã resolve, những lần `ldc` khác cùng tham chiếu **cùng mục run-time constant pool** sẽ nhận **cùng giá trị đã chọn** mà không gọi lại BSM. Nếu resolution đã thất bại, những lần dùng sau của **cùng symbolic reference** cũng tiếp tục thất bại mà không tự thử bootstrap lại. Trong tình huống nhiều thread cùng resolve lần đầu, BSM có thể chạy cạnh tranh; JVM chọn một kết quả để công bố.

## 2. `CONSTANT_Dynamic` chứa gì?

Một mục `CONSTANT_Dynamic_info` trong class file có cấu trúc:

```text
CONSTANT_Dynamic_info {
    u1 tag;                           // giá trị 17
    u2 bootstrap_method_attr_index;   // chỉ số trong BootstrapMethods
    u2 name_and_type_index;           // CONSTANT_NameAndType
}
```

`CONSTANT_NameAndType` chứa **tên hằng** và một **field descriptor** — ví dụ `Ljava/lang/String;`, `I`, `J` — không phải method descriptor.

**So sánh nhanh:**

| Thuộc tính | `CONSTANT_Dynamic` | `CONSTANT_InvokeDynamic` |
| --- | --- | --- |
| Tag trong constant pool | `17` | `18` |
| NameAndType descriptor | **Field descriptor** như `Ljava/lang/String;`, `I` | **Method descriptor** như `()Ljava/lang/String;` |
| Kết quả BSM | Giá trị của hằng, tương thích kiểu khai báo | `CallSite` có `type()` trùng method descriptor |
| Lệnh sử dụng | `ldc`, `ldc_w`, `ldc2_w`; cũng có thể là bootstrap argument của hằng/call site khác | `invokedynamic` |
| Phạm vi resolution | Một **symbolic reference / constant-pool entry** trong class đang được định nghĩa | Riêng từng **lexical `invokedynamic` instruction** |
| Số lần BSM thông thường sau khi resolve | Không gọi lại cho cùng entry | Không gọi lại cho cùng instruction |

Ví dụ `CONSTANT_Dynamic` mô tả một `String` tên `CHOSEN`:

```text
#20 = Dynamic #0:#19   // #0:CHOSEN:Ljava/lang/String;
                        // bootstrap index 0; NameAndType #19
```

Dòng này là dạng **trích yếu `javap`**. Mục `#20` không chứa ký tự `"choice-A"` hay `"choice-B"`; nó chứa một **công thức symbolic** gồm BSM index và name/type. JVM sẽ gọi BSM và kiểm tra kết quả, rồi giữ lại giá trị được chọn cho các lần dùng sau.

### 2.1. Ba tham số ngữ cảnh của bootstrap

BSM thường có chữ ký gần với:

```java
public static Object bootstrap(
        MethodHandles.Lookup caller,
        String name,
        Class<?> type) {
    // Tạo hoặc lấy giá trị hằng có kiểu phù hợp với type.
}
```

Đây là **trích đoạn minh họa** (chưa phải chương trình độc lập):

- `caller`: `Lookup` của class nơi constant-pool entry đang được phân giải, hỗ trợ các quy tắc access control.
- `name`: tên symbolic của hằng, chẳng hạn `"CHOSEN"`; **không** phải một field Java thật bắt buộc tồn tại.
- `type`: đối tượng `Class<?>` tương ứng với **field descriptor** của `CONSTANT_Dynamic`, chẳng hạn `String.class` hoặc `int.class`.

BSM có thể nhận thêm **static bootstrap arguments** sau ba tham số ngữ cảnh. JVM giải mã các arguments từ thuộc tính `BootstrapMethods` trước khi gọi bootstrap. Chữ ký BSM thực tế phải tương thích với cách gọi đó; không bắt buộc BSM phải trả `Object` trong mọi trường hợp nếu method-handle invocation conversions hợp lệ.

**Không nhầm `Class<?> type` của condy với `MethodType type` của `invokedynamic`.** Một hằng `String` khai báo kiểu giá trị `String.class`; một call site `()String` khai báo kiểu method `MethodType.methodType(String.class)`.

### 2.2. Khi nào hằng động khác hằng Java `static final`?

`static final` là một **field** với quy tắc khởi tạo riêng của class. Hằng động là **một symbolic entry trong constant pool**: lệnh `ldc` có thể lấy giá trị đã resolve của nó mà không cần ứng dụng khai báo một Java field cùng tên. Trong ví dụ dưới đây, không có trường `CHOSEN` trên class `CondyGenerated`.

Dù `CONSTANT_Dynamic` có tên **constant**, nếu giá trị được chọn là tham chiếu đến một object mutable, object đó có thể bị thay đổi nội bộ theo hợp đồng API của nó. Điều JVM lưu là **kết quả resolution / tham chiếu được chọn**, không phải tự động tạo deep copy hoặc đảm bảo object là immutable.

## 3. `ldc`, `ldc_w` và `ldc2_w` dùng hằng động ra sao?

Một hằng động được tải lên **operand stack** bởi nhóm lệnh `ldc`. Chữ “load constant” ở đây **không đồng nghĩa BSM chạy mỗi lần**.

| Instruction | Opcode | Operand | Với `CONSTANT_Dynamic` |
| --- | --- | --- | --- |
| `ldc` | `0x12` | Constant-pool index **1 byte** | Tải hằng kiểu **không phải `long`/`double`** vào operand stack |
| `ldc_w` | `0x13` | Constant-pool index **2 byte** | Giống `ldc`, nhưng hỗ trợ index lớn hơn |
| `ldc2_w` | `0x14` | Constant-pool index **2 byte** | Tải hằng `long` hoặc `double`, kể cả `CONSTANT_Dynamic` có descriptor `J` hay `D` |

Ví dụ bytecode (hình dạng của `javap -c`):

```text
0: ldc    #20      // Dynamic #0:CHOSEN:Ljava/lang/String;
2: areturn

0: ldc_w  #20      // Dynamic #0:CHOSEN:Ljava/lang/String;
3: areturn
```

Hai instruction trên **cùng tham chiếu entry `#20`** dù opcode có kích thước khác nhau. Khi `#20` được resolve thành một reference, cả hai lệnh đều nhận lại giá trị **cùng reference đó** trong phạm vi class/run-time constant pool tương ứng.

Với hằng kiểu `int`, sau `ldc/ldc_w`, JVM push giá trị `int`, và method có thể trả qua `ireturn`. Với `long` hoặc `double`, cần `ldc2_w` và phép trả như `lreturn`/`dreturn`.

**Không dùng `ldc_w` chỉ vì đây là hằng động.** Việc chọn `ldc` hay `ldc_w` chủ yếu do độ rộng constant-pool index; `ldc2_w` do **kiểu category 2** (`long`/`double`). Cả `ldc` và `ldc_w` đều có thể tham chiếu một `CONSTANT_Dynamic` kiểu `String` hoặc `int` hợp lệ.

### 3.1. Khi nào JVM resolve?

Để thực thi `ldc` cần biết giá trị của symbolic reference; nếu entry chưa resolve, JVM thực hiện resolution theo JVMS `5.4.3` và `5.4.3.6`. Trong nhiều thí nghiệm, BSM được quan sát khi lần đầu chạm lệnh `ldc` tương ứng. Tuy nhiên, đặc tả JVM cho phép một số giải pháp **eager resolution**; do vậy không nên xây logic ứng dụng phụ thuộc tuyệt đối vào “BSM chỉ có thể bắt đầu đúng ở dòng lệnh `ldc` đầu tiên”.

Điều có thể dựa vào là **hợp đồng sau khi resolution được chọn**: các lần resolve tiếp theo của cùng entry trả cùng kết quả (hoặc cùng trạng thái lỗi) mà không tái gọi BSM chỉ vì code lại tải hằng.

### 3.2. Constant-pool entry không phải một “factory call”

Nếu source/bytecode có mười lần `ldc #20`:

```text
ldc #20
ldc #20
...
ldc #20
```

điều đó **không** có nghĩa JVM buộc tạo mười object. Resolution thuộc về entry. Với một reference constant được chọn từ BSM, các lần dùng sau có thể quan sát **reference identity** bằng `==`. Trong ví dụ Java, BSM cố tình dùng `new String(...)` để tránh lẫn kết quả với interned string literal; hai method khác nhau sẽ lấy cùng object của entry đã resolve.

## 4. Quá trình resolution: lấy BSM, gọi BSM, xác thực giá trị

Theo JVMS `5.4.3.6`, việc resolve một dynamically computed constant gồm ba giai đoạn:

1. **Chuẩn bị bootstrap:** resolve `CONSTANT_MethodHandle` của BSM; resolve field descriptor thành `Class<?> type`; resolve các static bootstrap arguments nếu có.
2. **Gọi bootstrap method handle:** JVM cung cấp `Lookup` của caller, tên hằng, `Class<?>` kiểu hằng và các static arguments.
3. **Xác thực kết quả và chuyển sang kiểu của hằng:** kết quả bootstrap phải chuyển được sang kiểu `T` mà descriptor đã khai báo. Nếu thành công, JVM giữ **giá trị đã chọn** làm kết quả resolution.

Sơ đồ:

```text
ldc/ldc_w/ldc2_w -> symbolic CONSTANT_Dynamic
           |
           v
  Đọc BSM + name + field descriptor + static args
           |
           v
  Gọi BSM(Lookup, String, Class<?>, ...)
           |
           +-- BSM ném lỗi --------------> resolution FAILED
           |
           v
  Kiểm tra / chuyển kết quả sang kiểu T
           |
           +-- NPE/CCE khi conversion ---> BootstrapMethodError, FAILED
           |
           v
  Chọn và giữ giá trị T trong run-time constant pool
           |
           v
  Đẩy T lên stack mỗi lần ldc; không chạy lại BSM
```

### 4.1. Kết quả của bootstrap phải tương thích với descriptor

Ví dụ:

```java
// Trích đoạn bootstrap, descriptor của condy là Ljava/lang/String;.
return new String("choice-A"); // Hợp lệ: String thuộc kiểu yêu cầu.
```

Nếu BSM trả:

```java
return Integer.valueOf(7); // SAI nếu condy cần String.
```

thì JVM thực hiện conversion tương đương việc convert kết quả `Object` sang `String`. Do `Integer` không phải `String`, conversion phát sinh `ClassCastException`, và resolution thất bại bằng **`BootstrapMethodError`**.

Điều này **khác** với `ClassCastException` xảy ra khi application code tự ép một object đã tải thành công từ `ldc` sang kiểu khác. Khi descriptor đã không được đáp ứng trong chính quá trình bootstrap, lỗi ở **linkage/resolution**.

### 4.2. Hằng reference có thể nhận `null`

Nếu field descriptor của condy là **reference type**, chẳng hạn `Ljava/lang/String;`, BSM **có thể trả `null`**. `null` là kết quả hợp lệ của phép chuyển sang kiểu reference và được cache như **giá trị đã chọn**.

```java
// Trích đoạn: condy có descriptor Ljava/lang/String;.
return null; // Hợp lệ; các ldc tiếp theo nhận null đã được chọn.
```

Sau đó, nếu ứng dụng tự gọi method trên giá trị null, lỗi `NullPointerException` ở ứng dụng là **lỗi sử dụng giá trị**, không phải bootstrap-resolution failure.

### 4.3. Hằng primitive không được nhận `null`

Nếu descriptor là `I` (hằng kiểu `int`), BSM cần trả một giá trị mà conversion có thể đưa về `int`, ví dụ `Integer.valueOf(42)`. Trả `null` không thể unbox sang primitive; conversion ném `NullPointerException` và JVM biến tình huống này thành **`BootstrapMethodError`**.

```java
// Trích đoạn: condy có descriptor I.
return Integer.valueOf(42); // Hợp lệ, JVM lấy int 42.
// return null;              // Không hợp lệ, conversion thành int thất bại.
```

Không nên kết luận “BSM trả null luôn thất bại” hoặc “BSM trả null luôn thành một Java null”. Kết quả **phụ thuộc field descriptor**.

### 4.4. Dùng BSM có static arguments

Một BSM có thể được dùng với metadata tĩnh, ví dụ:

```java
// Chữ ký minh họa, không phải chương trình độc lập.
public static Object bootstrap(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        String prefix,
        int version) {
    return prefix + "-" + version;
}
```

Class file phải có entries hợp lệ trong `BootstrapMethods` cho static arguments, và lời gọi Method Handle phải tương thích. Các arguments này là **đầu vào của resolution**, không mặc định khiến BSM chạy mỗi lần `ldc`. Đối với numeric bootstrap arguments, đặc tả có quy tắc thích nghi thích hợp khi gọi bootstrap handle; khi viết bytecode thủ công, cần tuân thủ toàn bộ hợp đồng `5.4.3.6`.

## 5. Lưu kết quả đã chọn: phạm vi, identity và trạng thái bên ngoài

### 5.1. Cache thành công theo run-time constant pool entry

Giả sử class được load bởi loader `L1` có mục `#20` mô tả hằng `String` `CHOSEN`. Trong thí nghiệm:

```text
CondyGenerated.first(): ldc   #20
CondyGenerated.again(): ldc_w #20
```

BSM trả **`new String("choice-A")`**. Sau đó code đổi trạng thái nguồn thành `setting="B"` rồi gọi `again()`. Kết quả vẫn `choice-A` vì `#20` đã resolve. Hai kết quả từ `first()` và `again()` là cùng một tham chiếu, tức `a == b` bằng `true`.

**Không nhầm với Java `String.intern()`:** BSM tạo một `new String(...)` độc lập, nhưng runtime constant pool lưu reference đã chọn. Đây là **cache do resolution**, không phải bằng chứng String literal pool can thiệp.

### 5.2. Thay đổi một đối tượng được cache

Nếu BSM trả một `List` mutable, hằng động có descriptor tương thích và JVM cache **tham chiếu tới List**. Một caller có thể thay đổi nội dung List thông qua reference đó nếu API cho phép. Các `ldc` sau vẫn dùng **cùng reference**, nhưng quan sát có thể thấy List đã bị thay đổi.

Đó là khác biệt quan trọng giữa **“giá trị constant pool được chọn một lần”** và **“object chắc chắn immutable”**. Trong thiết kế BSM, thường nên chọn immutable object để hành vi dễ dự đoán.

### 5.3. Cache theo entry, không phải mỗi `ldc` instruction

Đây là điểm cần phân biệt kỹ với `invokedynamic`:

- Với **`CONSTANT_Dynamic`**, khi entry đã được resolve, những instruction khác nhau cùng tham chiếu entry đó đều lấy cùng kết quả.
- Với **`CONSTANT_InvokeDynamic`**, resolution của call site có phạm vi **từng lexical `invokedynamic` instruction**; hai instruction cùng trỏ tới một CP entry vẫn có thể tạo hai CallSite độc lập.

Bài toán **14.3** nói về **hằng động**. Không áp dụng máy móc quy tắc “mỗi instruction riêng” của `invokedynamic` vào `ldc CONSTANT_Dynamic`.

### 5.4. Class loader mới có tạo giá trị mới không?

Có, khi cùng bytes class file được **định nghĩa thành class identity mới** bởi defining class loader khác, class mới có **run-time constant pool riêng** và `CONSTANT_Dynamic` cần resolution riêng.

Điều đó không có nghĩa gọi lại một `ldc` cũ sẽ reset cache. Trong ví dụ, cùng tên class `CondyGenerated` nhưng được nạp bằng hai `Definer` khác nhau; lần thứ hai có thể chọn giá trị mới `choice-B`.

### 5.5. Một lưu ý về các lần resolve đồng thời

Nếu nhiều thread cùng chạm một hằng động chưa resolve, JVM **có thể** gọi bootstrap method handle đồng thời; JVM chọn kết quả của **một lần thực thi** và công bố nó cho các thread. Kết quả của những lần bootstrap khác bị bỏ qua. Vì vậy:

- **Không được dựa vào số lần chạy BSM bằng đúng một trong tình huống race.**
- Tránh side effects không idempotent ở bootstrap.
- Nếu bootstrap truy cập trạng thái dùng chung, cần thread-safety thích hợp.
- Điều quan trọng là **một kết quả resolution được công bố**, không phải mọi thread tự lưu một giá trị khác nhau cho cùng entry.

Thí nghiệm sau chạy **tuần tự** để có số đếm có thể kiểm chứng chính xác.

## 6. Lỗi phân giải: `BootstrapMethodError`, cache lỗi và các ngoại lệ khác

### 6.1. `BootstrapMethodError` có nghĩa gì?

`BootstrapMethodError` là subtype của `LinkageError`, thuộc nhánh `Error`:

```text
Throwable
 └── Error
      └── LinkageError
           └── BootstrapMethodError
```

Lỗi này có thể xuất hiện khi bootstrap hoặc việc resolve bootstrap arguments thất bại, hay khi BSM trả kết quả **không thể chuyển sang kiểu đã khai báo** của hằng động.

Không phải mọi `RuntimeException` phát sinh tại lệnh `ldc` đều là `BootstrapMethodError`. Cần xác định lỗi đến từ **resolution/BSM** hay từ **code sử dụng giá trị sau khi `ldc` đã thành công**.

### 6.2. Bootstrap ném exception không phải `Error`

Nếu BSM ném:

```java
throw new IllegalStateException("not ready");
```

thì JVMS quy định resolution thất bại bằng `BootstrapMethodError` có `cause` là `IllegalStateException` ban đầu.

Ngược lại, nếu BSM trực tiếp ném một instance `Error` (chẳng hạn `AssertionError`), quy tắc không nhất thiết bọc nó vào `BootstrapMethodError`: `Error` đó có thể là error của resolution. Nếu việc **resolve BSM method handle** hoặc static argument thất bại ngay từ trước khi vào thân BSM, lỗi quan sát được còn phụ thuộc chính xác vào giai đoạn resolution.

### 6.3. Hằng trả sai kiểu hoặc primitive null

Hai lỗi quan trọng:

| Hằng yêu cầu | BSM trả | Kết quả |
| --- | --- | --- |
| `String` | `new String("abc")` | Thành công, cache reference |
| `String` | `null` | Thành công, cache `null` |
| `String` | `Integer.valueOf(7)` | `BootstrapMethodError` do conversion bị `ClassCastException` |
| `int` | `Integer.valueOf(42)` | Thành công, cache giá trị `int 42` |
| `int` | `null` | `BootstrapMethodError` do conversion bị `NullPointerException` |
| `int` | Một object không unbox/cast thích hợp | Có thể lỗi conversion dẫn tới `BootstrapMethodError` |

Các `cause` cụ thể trong chương trình thử nghiệm đã được kiểm chứng. Khi làm diagnostic chung, ưu tiên đọc cause chain thay vì đoán rằng mọi BME bắt buộc có cùng message.

### 6.4. Sau khi resolution thất bại có tự retry không?

**Không, đối với cùng symbolic reference đã thất bại.** Theo JVMS `5.4.3`:

- Những lần resolve tiếp theo của entry ấy tiếp tục thất bại bằng lỗi resolution đã ghi nhận.
- Bootstrap method **không được thực thi lại** chỉ vì caller `catch` lỗi rồi thử `ldc` lần nữa.
- Cờ như `failReady` đổi từ `false` sang `true` sau lần lỗi **không cứu được entry đã failed**.
- Một **method khác** cùng `ldc` entry cũng chịu lỗi cached; không phải “method mới = hằng mới”.

Đây là khác biệt lớn với cơ chế retry nghiệp vụ thông thường. Viết vòng lặp:

```java
// Trích đoạn SAI về chiến lược retry condy.
for (int i = 0; i < 3; i++) {
    try {
        return readDynamicConstant(); // Cùng CP entry đã failed.
    } catch (BootstrapMethodError ex) {
        // Không có bảo đảm BSM sẽ được chạy lại.
    }
}
```

không tạo ra ba cơ hội bootstrap. Nếu entry đã failed ở lượt đầu, các lượt tiếp theo chỉ nhận lại error. Đoạn mã trên còn chỉ là **pseudocode Java fragment**, không phải method hoàn chỉnh.

### 6.5. Lỗi vòng lặp phụ thuộc giữa dynamic constants

`CONSTANT_Dynamic` có thể xuất hiện làm static bootstrap argument của một dynamic constant khác. Class file có thể biểu diễn chu trình như:

```text
A: CONSTANT_Dynamic, BSM argument tham chiếu B
B: CONSTANT_Dynamic, BSM argument tham chiếu A
```

JVMS không cho phép resolve một dynamically-computed constant **phụ thuộc chính nó**, trực tiếp hoặc gián tiếp qua static bootstrap arguments. Lúc cần resolve lại entry trong chu trình, resolution thất bại bằng **`StackOverflowError`**. Đừng viết bytecode generator tạo dependency cycle rồi kỳ vọng JVM chọn một giá trị tạm như `null`.

Điểm này khác với các graph phụ thuộc hợp lệ không có chu trình; những BSM static arguments loại condy sẽ được resolve theo quy tắc trước khi BSM nhận giá trị.

### 6.6. Phân biệt lớp lỗi

| Hiện tượng | Tầng có thể gây lỗi | Gợi ý kiểm tra |
| --- | --- | --- |
| `BootstrapMethodError`, cause `IllegalStateException` | Logic BSM ném exception | Code BSM, trạng thái/config lúc đầu resolve |
| `BootstrapMethodError`, cause `ClassCastException` | BSM trả giá trị sai descriptor reference | `CONSTANT_NameAndType` field descriptor, type của object trả |
| `BootstrapMethodError`, cause `NullPointerException` | Hằng primitive được bootstrap trả null | Descriptor `I`/`J`/... và boxing/unboxing |
| `NoClassDefFoundError` / `IllegalAccessError` | Resolve class, method handle hoặc module access control | Dependency, class loader, JPMS, visibility |
| `ClassFormatError` / `VerifyError` | Class file / bytecode không hợp lệ | Major version, constant-pool tag/index, Code attribute |
| `StackOverflowError` khi condy phụ thuộc chu kỳ | Recursive constant resolution | Static BSM arguments và dependency graph |
| `NullPointerException` từ code sau khi load reference null | **Sử dụng giá trị** đã resolve thành công | Có kiểm tra null trước khi gọi method không? |
| `InvocationTargetException` khi gọi generated method bằng Reflection | Wrapper của Reflection | `getCause()` để nhìn lỗi của `ldc`/application |

Lỗi resolution không đồng nghĩa tất cả lỗi của ứng dụng đều được “cache vĩnh viễn”. Những exception **xảy ra sau khi `ldc` đã đẩy giá trị thành công** là logic sử dụng value; lệnh `ldc` vẫn tiếp tục trả về hằng đã được chọn ở lần sau.

## 7. Thực nghiệm tự phát sinh class file: `ldc`, `ldc_w` và các kết quả cached

### 7.1. Mô tả thí nghiệm

Ta sẽ tạo class runtime tên **`CondyGenerated`** từ một `byte[]` có **classfile major version 55**. Class này không cần Java source tương ứng, và có mười method public static:

| Method | Dynamic constant dùng | Mục đích |
| --- | --- | --- |
| `first()` | `CHOSEN`, `ldc` | Chọn lần đầu `choice-A` |
| `again()` | **cùng `CHOSEN`**, `ldc_w` | Nhận cùng reference dù `setting` đã đổi |
| `fail()` | `FAIL` | BSM ném `IllegalStateException` |
| `failAgain()` | **cùng `FAIL`** | Chứng minh lỗi đã cache giữa hai method |
| `nullable()` | `NULL` kiểu `String` | BSM chọn `null` hợp lệ |
| `nullAgain()` | **cùng `NULL`** | `null` vẫn được cache dù BSM sau đó có thể trả giá trị khác |
| `wrong()` | `WRONG` kiểu `String` | BSM trả `Integer`, gây lỗi conversion |
| `number()` | `INT` kiểu `int` | BSM trả wrapper `Integer(42)`, convert thành primitive |
| `numberAgain()` | **cùng `INT`** | Chứng minh cache của primitive |
| `nullNumber()` | `NULL_INT` kiểu `int` | Trả null cho primitive, gây `BootstrapMethodError` |

Mỗi constant-pool entry có tên riêng hoặc được chia sẻ có chủ ý. Các mode khác nhau được chọn bằng tham số `name` của cùng một BSM để dễ theo dõi và đo **số lần bootstrap chạy**.

### 7.2. Mã Java 17+ đầy đủ

Tạo file **`CondyResolutionLab.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class CondyResolutionLab {
    private static String setting = "A";
    private static boolean failReady;
    private static boolean nullAllowed = true;
    private static int chosenRuns, failRuns, nullRuns, wrongRuns, intRuns, nullIntRuns;

    public static Object bootstrap(MethodHandles.Lookup caller,
                                   String name, Class<?> type) {
        return switch (name) {
            case "CHOSEN" -> {
                chosenRuns++;
                yield new String("choice-" + setting);
            }
            case "FAIL" -> {
                failRuns++;
                if (!failReady) throw new IllegalStateException("not ready");
                yield "recovered";
            }
            case "NULL" -> {
                nullRuns++;
                yield nullAllowed ? null : "later-value";
            }
            case "WRONG" -> {
                wrongRuns++;
                yield Integer.valueOf(7); // Required: String, actual: Integer
            }
            case "INT" -> {
                intRuns++;
                yield Integer.valueOf(42);
            }
            case "NULL_INT" -> {
                nullIntRuns++;
                yield null; // primitive int cannot be null
            }
            default -> throw new IllegalArgumentException(name);
        };
    }

    static final class Pool {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        private final DataOutputStream out = new DataOutputStream(bytes);
        private int nextIndex = 1;

        int utf(String value) throws IOException {
            int i = nextIndex++;
            out.writeByte(1);
            out.writeUTF(value);
            return i;
        }

        int clazz(int name) throws IOException {
            int i = nextIndex++;
            out.writeByte(7);
            out.writeShort(name);
            return i;
        }

        int nat(int name, int descriptor) throws IOException {
            int i = nextIndex++;
            out.writeByte(12);
            out.writeShort(name);
            out.writeShort(descriptor);
            return i;
        }

        int methodRef(int owner, int nat) throws IOException {
            int i = nextIndex++;
            out.writeByte(10);
            out.writeShort(owner);
            out.writeShort(nat);
            return i;
        }

        int methodHandle(int refKind, int ref) throws IOException {
            int i = nextIndex++;
            out.writeByte(15);
            out.writeByte(refKind);
            out.writeShort(ref);
            return i;
        }

        int dynamic(int bsmIndex, int nameAndType) throws IOException {
            int i = nextIndex++;
            out.writeByte(17);
            out.writeShort(bsmIndex);
            out.writeShort(nameAndType);
            return i;
        }

        void writeTo(DataOutputStream target) throws IOException {
            target.writeShort(nextIndex);
            target.write(bytes.toByteArray());
        }
    }

    record GeneratedMethod(int name, int descriptor, int constant,
                           boolean wide, int returnOpcode) {}

    static final class Definer extends ClassLoader {
        Definer() {
            super(CondyResolutionLab.class.getClassLoader());
        }

        Class<?> define(byte[] bytes) {
            return defineClass("CondyGenerated", bytes, 0, bytes.length);
        }
    }

    private static byte[] generate() throws IOException {
        Pool cp = new Pool();

        int thisClass = cp.clazz(cp.utf("CondyGenerated"));
        int superClass = cp.clazz(cp.utf("java/lang/Object"));
        int code = cp.utf("Code");
        int bootstrapMethods = cp.utf("BootstrapMethods");
        int host = cp.clazz(cp.utf("CondyResolutionLab"));
        int bootstrapName = cp.utf("bootstrap");
        int bootstrapDesc = cp.utf(
                "(Ljava/lang/invoke/MethodHandles$Lookup;"
                + "Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;");
        int ref = cp.methodRef(host, cp.nat(bootstrapName, bootstrapDesc));
        int bsmHandle = cp.methodHandle(6, ref); // REF_invokeStatic

        int stringDesc = cp.utf("Ljava/lang/String;");
        int intDesc = cp.utf("I");
        int stringMethod = cp.utf("()Ljava/lang/String;");
        int intMethod = cp.utf("()I");

        int chosen = cp.dynamic(0, cp.nat(cp.utf("CHOSEN"), stringDesc));
        int fail = cp.dynamic(0, cp.nat(cp.utf("FAIL"), stringDesc));
        int nullable = cp.dynamic(0, cp.nat(cp.utf("NULL"), stringDesc));
        int wrong = cp.dynamic(0, cp.nat(cp.utf("WRONG"), stringDesc));
        int primitive = cp.dynamic(0, cp.nat(cp.utf("INT"), intDesc));
        int nullPrimitive = cp.dynamic(
                0, cp.nat(cp.utf("NULL_INT"), intDesc));

        List<GeneratedMethod> methods = List.of(
            new GeneratedMethod(
                    cp.utf("first"), stringMethod, chosen, false, 0xb0),
            new GeneratedMethod(
                    cp.utf("again"), stringMethod, chosen, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("fail"), stringMethod, fail, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("failAgain"), stringMethod, fail, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("nullable"), stringMethod, nullable, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("nullAgain"), stringMethod, nullable, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("wrong"), stringMethod, wrong, true, 0xb0),
            new GeneratedMethod(
                    cp.utf("number"), intMethod, primitive, true, 0xac),
            new GeneratedMethod(
                    cp.utf("numberAgain"), intMethod, primitive, true, 0xac),
            new GeneratedMethod(
                    cp.utf("nullNumber"), intMethod, nullPrimitive, true, 0xac)
        );

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.writeInt(0xCAFEBABE);
        out.writeShort(0);
        out.writeShort(55); // Java 11+, CONSTANT_Dynamic supported
        cp.writeTo(out);
        out.writeShort(0x0021); // public | super
        out.writeShort(thisClass);
        out.writeShort(superClass);
        out.writeShort(0); // interfaces
        out.writeShort(0); // fields
        out.writeShort(methods.size());

        for (GeneratedMethod m : methods) {
            out.writeShort(0x0009); // public static
            out.writeShort(m.name());
            out.writeShort(m.descriptor());
            out.writeShort(1); // one Code attribute
            out.writeShort(code);
            int length = m.wide() ? 4 : 3;
            out.writeInt(12 + length);
            out.writeShort(1); // maxStack
            out.writeShort(0); // maxLocals
            out.writeInt(length);
            out.writeByte(m.wide() ? 0x13 : 0x12); // ldc_w / ldc
            if (m.wide()) out.writeShort(m.constant());
            else out.writeByte(m.constant());
            out.writeByte(m.returnOpcode());
            out.writeShort(0); // exception table
            out.writeShort(0); // nested code attributes
        }

        out.writeShort(1); // class attributes
        out.writeShort(bootstrapMethods);
        out.writeInt(6);
        out.writeShort(1); // one bootstrap entry
        out.writeShort(bsmHandle);
        out.writeShort(0); // no static arguments
        out.flush();
        return bytes.toByteArray();
    }

    private static Object call(Class<?> owner, String method) throws Throwable {
        Method m = owner.getMethod(method);
        try {
            return m.invoke(null);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes = generate();
        Files.write(Path.of("CondyGenerated.class"), bytes);
        Class<?> c1 = new Definer().define(bytes);

        Object a = call(c1, "first");
        System.out.println("first=" + a);
        setting = "B";
        Object b = call(c1, "again");
        System.out.println("again=" + b);
        System.out.println("same identity=" + (a == b));
        System.out.println("chosen calls=" + chosenRuns);

        try {
            call(c1, "fail");
        } catch (BootstrapMethodError ex) {
            System.out.println("fail=" + ex.getClass().getSimpleName());
            System.out.println("fail cause="
                    + ex.getCause().getClass().getSimpleName());
        }
        failReady = true;
        try {
            call(c1, "failAgain");
        } catch (BootstrapMethodError ex) {
            System.out.println("retry=" + ex.getClass().getSimpleName());
        }
        System.out.println("failed bootstrap calls=" + failRuns);

        System.out.println("nullable first=" + call(c1, "nullable"));
        nullAllowed = false;
        System.out.println("nullable again=" + call(c1, "nullAgain"));
        System.out.println("null bootstrap calls=" + nullRuns);

        try {
            call(c1, "wrong");
        } catch (BootstrapMethodError ex) {
            System.out.println("wrong=" + ex.getClass().getSimpleName());
            System.out.println("wrong cause="
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("wrong bootstrap calls=" + wrongRuns);

        System.out.println("number=" + call(c1, "number"));
        System.out.println("number again=" + call(c1, "numberAgain"));
        System.out.println("integer bootstrap calls=" + intRuns);

        try {
            call(c1, "nullNumber");
        } catch (BootstrapMethodError ex) {
            System.out.println("null int=" + ex.getClass().getSimpleName());
            System.out.println("null int cause="
                    + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("null int bootstrap calls=" + nullIntRuns);

        Class<?> c2 = new Definer().define(bytes);
        System.out.println("new loader=" + call(c2, "first"));
        System.out.println("chosen calls after reload=" + chosenRuns);
    }
}
```

**Giải thích các phần của code:**

- `Pool` ghi các constant-pool entries với tags đúng định dạng JVM: UTF8 (`1`), Class (`7`), NameAndType (`12`), Methodref (`10`), MethodHandle (`15`), Dynamic (`17`).
- `Pool.dynamic(...)` viết bootstrap-table index và name-and-type index, **không** chứa giá trị resolved.
- `methodHandle(6, ref)` dùng reference kind `REF_invokeStatic` để chỉ tới BSM.
- `generate()` tạo classfile **major 55**, đủ hỗ trợ `CONSTANT_Dynamic`, với `BootstrapMethods` trỏ tới BSM.
- `GeneratedMethod` chỉ mô tả một method rất ngắn: `ldc` hoặc `ldc_w` rồi `areturn`/`ireturn`. Không có nhánh điều kiện hay exception handler trong bytecode sinh ra.
- `call(...)` dùng Reflection để gọi method trên class sinh ra; `InvocationTargetException` được unwrap để bài học in được **lỗi JVM thực sự**.
- `Definer` tạo một class identity riêng cho mỗi defining class loader; đây là công cụ quan sát cache riêng của từng class.

Ví dụ là một **chương trình hoàn chỉnh**, không phải pseudocode. Nó có thể chạy với `javac`/`java` từ **JDK 17 trở lên** mà không cần `--add-opens`/`--add-exports`.

### 7.3. Biên dịch và chạy

Từ thư mục có file `CondyResolutionLab.java`:

```bash
javac CondyResolutionLab.java
java CondyResolutionLab
```

Chương trình còn ghi `CondyGenerated.class` vào thư mục làm việc để bạn có thể tự kiểm tra bằng `javap`.

**Stdout chính xác đã được kiểm chứng bằng chạy thực tế:**

```text
first=choice-A
again=choice-A
same identity=true
chosen calls=1
fail=BootstrapMethodError
fail cause=IllegalStateException
retry=BootstrapMethodError
failed bootstrap calls=1
nullable first=null
nullable again=null
null bootstrap calls=1
wrong=BootstrapMethodError
wrong cause=ClassCastException
wrong bootstrap calls=1
number=42
number again=42
integer bootstrap calls=1
null int=BootstrapMethodError
null int cause=NullPointerException
null int bootstrap calls=1
new loader=choice-B
chosen calls after reload=2
```

**Điều kiện kết quả:** chương trình cố ý chạy **tuần tự** và trên JDK đã kiểm thử. Nếu JVM chủ động resolve sớm hoặc thực hiện cạnh tranh trong một môi trường khác, thời điểm bootstrap có thể khác; các quy tắc resolution của JVM vẫn là tiêu chuẩn cần bám theo. Trên bài thử đã chạy, 22 dòng stdout ở trên ổn định và không chứa tên class loader ngẫu nhiên.

### 7.4. Dùng `javap` kiểm tra class file thực sự có condy

Chạy tiếp:

```bash
javap -v -c CondyGenerated.class
```

Trong output, tìm:

```text
major version: 55
#20 = Dynamic  #0:#19  // CHOSEN:Ljava/lang/String;
#23 = Dynamic  #0:#22  // FAIL:Ljava/lang/String;
#26 = Dynamic  #0:#25  // NULL:Ljava/lang/String;
#29 = Dynamic  #0:#28  // WRONG:Ljava/lang/String;
#32 = Dynamic  #0:#31  // INT:I
#35 = Dynamic  #0:#34  // NULL_INT:I

first():      ldc    #20
again():      ldc_w  #20
fail():       ldc_w  #23
failAgain():  ldc_w  #23
nullable():   ldc_w  #26
nullAgain():  ldc_w  #26
wrong():      ldc_w  #29
number():     ldc_w  #32
numberAgain():ldc_w  #32
nullNumber(): ldc_w  #35
```

Đây là **trích yếu từ `javap`**, không phải nguyên văn tất cả dòng: output thực còn có các khai báo method, flags, constant-pool descriptions và thuộc tính `BootstrapMethods`. Các chỉ số `#20`, `#23`, `#26`, `#29`, `#32`, `#35` được xác nhận từ classfile của mã thí nghiệm này.

Đặc biệt, `first` và `again` dùng cùng `#20`; `fail` và `failAgain` dùng cùng `#23`. Đó là bằng chứng cấp bytecode cho việc **hai method khác nhau cùng tham chiếu một dynamic constant pool entry**.

## 8. Giải thích kết quả: vì sao BSM không chạy lại?

### 8.1. `CHOSEN`: cùng tham chiếu đã được chọn

`first()` tải `#20` khi `setting="A"`; BSM chạy một lần và tạo `new String("choice-A")`. `again()` dùng cùng `#20` sau khi `setting="B"`:

```text
first=choice-A
again=choice-A
same identity=true
chosen calls=1
```

Kết quả không phải `choice-B` vì BSM không được gọi lại. `same identity=true` còn chứng minh JVM giữ **đúng reference** được chọn, không chỉ một chuỗi mới có nội dung bằng nhau.

### 8.2. `FAIL`: lỗi được lưu theo entry, kể cả qua method khác

`fail()` dùng `#23` khi `failReady=false`. BSM tăng counter rồi ném `IllegalStateException("not ready")`. JVM báo `BootstrapMethodError`.

Sau đó `failReady=true` nhưng `failAgain()`, method **khác** cùng dùng `#23`, vẫn nhận lỗi resolution:

```text
fail=BootstrapMethodError
fail cause=IllegalStateException
retry=BootstrapMethodError
failed bootstrap calls=1
```

Điểm phân biệt: **lỗi được ghi nhận cho mục `CONSTANT_Dynamic`**. Không có “một BSM riêng cho mỗi bytecode `ldc`” khi hai `ldc` cùng tham chiếu mục đó.

Nếu cần thử lại bootstrap sau khi sửa cấu hình, một cách kiểm chứng là tạo **class identity mới** hoặc chạy một **JVM mới**; đừng coi `catch` rồi lặp lại method là giải pháp.

### 8.3. `NULL`: reference null là giá trị được cache

Hằng `#26` có descriptor `String`. BSM trả null lần đầu; `nullAllowed` sau đó chuyển thành false, nhưng lần gọi qua `nullAgain()` vẫn lấy null cached:

```text
nullable first=null
nullable again=null
null bootstrap calls=1
```

Đây là **resolution thành công**, không phải failed state. `null` hợp lệ cho reference type. Tùy business logic, caller nhận null rồi có thể cần tự kiểm tra null trước khi sử dụng.

### 8.4. `WRONG`: trả sai kiểu bị phát hiện ở giai đoạn resolution

`wrong()` tải mục `#29`, descriptor `String`; BSM trả `Integer.valueOf(7)`. Conversion thành `String` thất bại:

```text
wrong=BootstrapMethodError
wrong cause=ClassCastException
wrong bootstrap calls=1
```

Ứng dụng không hề nhận một `Integer` từ `ldc` rồi mới tự cast. JVM đã kiểm tra kết quả bootstrap **trước khi lệnh tải hằng có thể hoàn tất**.

### 8.5. `INT`: hằng primitive được cache

Mục `#32` khai báo kiểu `int`, BSM trả `Integer.valueOf(42)`. JVM chuyển sang giá trị primitive và lưu kết quả:

```text
number=42
number again=42
integer bootstrap calls=1
```

Khác với `String` reference, kiểm thử ở đây quan sát **cùng giá trị `int`** và **counter bootstrap** chứ không dùng `==` trên boxed Integer để chứng minh identity (Integer caching của Java có thể gây nhầm lẫn).

### 8.6. `NULL_INT`: primitive null dẫn tới `BootstrapMethodError`

Mục `#35` có field descriptor `I`. BSM trả null; conversion không thể unbox thành primitive:

```text
null int=BootstrapMethodError
null int cause=NullPointerException
null int bootstrap calls=1
```

Đây là lỗi **giá trị bootstrap không hợp lệ cho kiểu đã khai báo**, không phải lỗi caller truy cập object null sau một `ldc` thành công.

### 8.7. Defining loader mới: constant pool mới

Đoạn cuối tạo một `Definer` mới, định nghĩa lại **cùng bytecode** dưới class identity khác. `setting` vẫn là `"B"`:

```text
new loader=choice-B
chosen calls after reload=2
```

Hằng `CHOSEN` của class **mới** được resolve thành giá trị mới. Điều đó **không xóa hoặc thay đổi giá trị `choice-A`** đã cache ở class cũ. Nếu bạn tiếp tục gọi `first()` trên `c1`, nó vẫn trả giá trị ban đầu, không chọn lại `choice-B`.

## 9. Phân biệt condy với `invokedynamic` để không hiểu sai cache

Cả hai cơ chế đều dùng bootstrap và constant pool; tuy nhiên **đối tượng mà JVM ghi nhớ sau resolution khác nhau**:

| Thuộc tính | Dynamic constant (`condy`) | `invokedynamic` |
| --- | --- | --- |
| Mục CP | `CONSTANT_Dynamic`, tag `17` | `CONSTANT_InvokeDynamic`, tag `18` |
| Descriptor | Field descriptor `String`/`int`/`long`... | Method descriptor như `(String)int` |
| BSM nhận loại “type” | `Class<?>` | `MethodType` |
| BSM cần trả | **Giá trị** tương thích type | **CallSite** đúng method type |
| Bytecode | `ldc`, `ldc_w`, `ldc2_w` | `invokedynamic` |
| Phạm vi cache | Một symbolic reference trong **run-time constant pool** | **Từng lexical instruction** |
| Hai opcode cùng mục CP | Dùng chung kết quả condy | Có thể có CallSite liên kết độc lập |
| BSM trả null | Có thể hợp lệ với reference constant | Không phải CallSite hợp lệ |
| Sau thất bại | Không tự gọi lại BSM cho cùng entry | Không tự gọi lại BSM cho cùng instruction |

Một lỗi thường gặp là thấy `invokedynamic` hai lần cùng trỏ một constant-pool entry có thể link khác nhau, rồi áp dụng kết luận ấy cho `ldc #20`. **Không đúng.** Hai `ldc` của cùng class trỏ tới một `CONSTANT_Dynamic #20` dùng chung resolution result, như `first()/again()` trong ví dụ.

Ngược lại, đừng giả định mỗi lần dùng một lambda (thường liên quan `invokedynamic`) sẽ trả về cùng object lambda chỉ vì call site được cache; call site có thể là một **factory target** được gọi nhiều lần. Với condy, **chính giá trị** được chọn và lưu trong constant pool. Đây là sự khác biệt về hợp đồng của hai loại bootstrap.

## 10. Các trường hợp biên khi viết classfile hoặc bootstrap

### 10.1. `ldc2_w` đối với `long` và `double`

Nếu `CONSTANT_Dynamic` có field descriptor `J` hoặc `D`, hãy phát ra **`ldc2_w`** thay vì `ldc` hoặc `ldc_w`. Ví dụ minh họa ở dạng disassembly:

```text
#60 = Dynamic #0:#59 // COMPUTED_LONG:J

0: ldc2_w #60
3: lreturn
```

Dòng `#60` là **ví dụ giả định độc lập**, không nằm trong classfile của chương trình mục 7. Một BSM trả `Long.valueOf(123456789L)` tương thích với descriptor `J` có thể cung cấp giá trị `long` để `ldc2_w` đẩy lên operand stack.

Chú ý: `ldc_w` có index 2 byte nhưng vẫn **không** thay cho `ldc2_w` khi kiểu hằng là `long`/`double`. “Wide” của index và “category 2 value” là **hai khái niệm khác nhau**.

### 10.2. Sai version, tag hoặc descriptor

`CONSTANT_Dynamic` yêu cầu classfile hỗ trợ từ Java 11 (major version **55**). Nếu một generator dùng classfile version quá cũ nhưng ghi tag `17`, JVM có thể báo `ClassFormatError` hoặc lỗi classfile tương ứng **trước khi BSM có cơ hội chạy**.

Kiểm tra:

```bash
javap -v -c CondyGenerated.class
```

Tìm major version, `Dynamic`, `BootstrapMethods` và instruction `ldc`. Nếu `javap` không thể parse file, kiểm tra số lượng constant-pool entries, `Code.attribute_length`, method descriptors và các u1/u2 fields, không tự giả định lỗi đến từ bootstrap logic.

### 10.3. Bootstrap arguments phụ thuộc nhau

Một static bootstrap argument có thể là một condy khác; nó phải được resolve theo quy tắc trước khi BSM ngoài nhận giá trị. Nếu dependency không tồn tại, sai type, hoặc tạo chu kỳ, BSM ngoài có thể không chạy được.

Khi debug một BSM “không thấy log”, đừng chỉ kiểm tra thân BSM đó. JVM có thể đang thất bại **trong quá trình resolve arguments / bootstrap method handle** trước khi vào code.

### 10.4. Kết quả reference là object nào?

BSM có thể trả:

- Immutable object (thường dễ dùng nhất).
- Class mirror, MethodHandle, VarHandle hoặc những object phù hợp với field descriptor.
- Mutable object (caller có thể quan sát sự thay đổi bên trong, nhưng reference cached vẫn là reference đã chọn).
- Null đối với reference descriptor.

Chỉ có **một giá trị resolution được chọn** cho entry. Điều đó không có nghĩa mọi tham chiếu đến nội dung cùng tên ở các class khác nhau/loader khác nhau đều được intern thành một global singleton.

### 10.5. BSM không phải constructor của mỗi lần sử dụng

Nếu bạn cần **một object mới mỗi lần caller gọi method**, không nên dùng condy để gọi `new` qua bootstrap và mong `ldc` làm điều đó liên tục. Một lần bootstrap tạo một object rồi cache, các `ldc` sau **tái sử dụng tham chiếu**. Với nhu cầu factory mỗi lần gọi, sử dụng lời gọi method/factory bình thường hoặc một `MethodHandle`/`invokedynamic` target thích hợp.

### 10.6. Không dựa vào retry của một lỗi bootstrap nhất thời

BSM không phù hợp với lỗi transient có thể phục hồi tại cùng entry bằng retry tự động. Ví dụ BSM đọc mạng và ném I/O exception ở lần resolution đầu thì entry có thể bị “đóng băng” ở lỗi. Nếu phải phục hồi logic nghiệp vụ, thiết kế BSM **trả kết quả hợp lệ ổn định** (ví dụ một immutable handle tới service) rồi đặt logic retry ở tầng sử dụng; hoặc thiết kế lại nơi khởi tạo.

Việc cho BSM fallback sang một giá trị giả cũng có rủi ro: giá trị giả có thể được **cache lâu dài** như kết quả chính thức. Không nên che giấu lỗi cấu hình nghiêm trọng chỉ để tránh `BootstrapMethodError`.

## 11. Quy trình chẩn đoán `BootstrapMethodError` ở `ldc`

Khi gặp lỗi runtime liên quan condy, hãy đi qua checklist:

1. **Ghi class identity và Java version.** Class nào chứa `ldc`? Được định nghĩa bởi loader nào? Có custom loader/agent/bytecode transformer không?
2. **Kiểm tra bytecode thật bằng `javap -v -c`.** Xác nhận có `CONSTANT_Dynamic` tag `17`, field descriptor đúng, bootstrap method handle index và `BootstrapMethods` phù hợp.
3. **Đọc đúng cause chain.** `BootstrapMethodError.getCause()` có thể tiết lộ `IllegalStateException`, `ClassCastException`, `NullPointerException`. Nếu gọi qua Reflection thì `InvocationTargetException` là wrapper ở tầng khác.
4. **Xác định BSM đã chạy chưa.** Lỗi có thể đến từ resolve method handle, class descriptor hoặc static arguments trước thân BSM.
5. **Kiểm tra kiểu trả và null.** Reference có thể null; primitive không. Object trả có phù hợp `Class<?> type` không?
6. **Phân biệt resolve lần đầu và lần dùng lại.** BSM counter đứng yên sau lỗi không phải vấn đề logger; đó có thể là trạng thái failed resolution đã được cache.
7. **Nếu đã sửa nguồn lỗi, thử trong class/JVM mới.** Không dùng cùng entry failed để kết luận bản sửa không hoạt động.
8. **Xem concurrency.** Nhiều BSM executions tại lần đầu cạnh tranh được JVMS cho phép; test tuần tự trước khi phân tích race.
9. **Đừng nhầm với `invokedynamic`.** Với condy, kết quả cached theo entry, không phải từng opcode `ldc`.
10. **Chỉ thay code ở đúng tầng.** Nếu classfile invalid, sửa generator; nếu BSM sai type, sửa BSM; nếu target application dùng null sai, sửa caller; nếu class loader gây incompatibility, sửa runtime graph.

### 11.1. Triệu chứng và cách xử lý nhanh

| Quan sát | Diễn giải | Cách sửa |
| --- | --- | --- |
| `first()` và `again()` luôn trả cùng String dù config đổi | Cùng dynamic CP entry đã resolve | Nếu cần thay đổi theo thời gian, đừng biểu diễn bằng condy cached value |
| `failAgain()` vẫn BME sau khi `failReady=true` | Failed resolution đã cache | Dùng class/JVM identity mới khi kiểm chứng; sửa BSM cho lần link đầu |
| Hằng String từ BSM có giá trị null | Reference-null resolution hợp lệ | Caller tự xử lý null; đây không mặc nhiên là linkage failure |
| Hằng int trả null dẫn tới BME | Primitive conversion không chấp nhận null | BSM phải trả giá trị unbox hợp lệ |
| `ClassCastException` nằm trong cause của BME | Object BSM trả sai declared type | Kiểm tra `NameAndType` descriptor và bootstrap result |
| Không thấy log từ BSM | Có thể lỗi ở bước resolve BSM/arguments | Đọc classfile, cause, access control |
| `StackOverflowError` trong resolution | Dependency condy bị vòng lặp | Làm acyclic static arguments |
| Nạp cùng class bằng loader mới cho kết quả khác | Pool của class identity mới | Không hiểu nhầm thành retry ở class cũ |
| `ldc_w` được phát cho descriptor `J` | Sai instruction category | Dùng `ldc2_w` |
| Một method muốn object mới mỗi lần nhưng nhận lại cùng object | `ldc` đang dùng condy cached reference | Dùng factory/method call thay vì condy |

## 12. Thiết kế bootstrap an toàn, xác định và dễ kiểm thử

Một BSM chất lượng tốt nên:

- **Xác thực `name` và `type` sớm.** Không bỏ qua field descriptor rồi trả bừa object. Có thể chủ động ném exception mô tả sai config, nhưng hiểu rằng error đó sẽ ảnh hưởng tới resolution và các lần dùng sau.
- **Giảm side effects**: startup metrics, ghi file, network hoặc thay đổi trạng thái global trong BSM khó dự đoán hơn vì JVM có thể resolve sớm, hoặc chạy nhiều invocation cạnh tranh.
- **Trả immutable value nếu phù hợp** để cache kết quả không mang theo trạng thái mutable ngoài ý muốn.
- **Tránh phụ thuộc tạm thời**: nếu service/config chưa sẵn sàng, cân nhắc tách việc khởi tạo thực sang một API có retry, thay vì để condy resolution bị thất bại.
- **Kiểm tra quyền truy cập** khi dùng `MethodHandles.Lookup` từ caller. BSM không tự mở module/private members.
- **Không bỏ qua nguyên nhân lỗi**: khi log BME, ghi cả `getCause()`, class loader và NameAndType phù hợp, tránh mất dấu sai kiểu/đường load.
- **Kiểm thử cả cached success và cached failure**: dùng hai method cùng CP entry, thay trạng thái sau resolution, đo số lần BSM gọi.
- **Kiểm thử class identity mới**: nếu test cần reset linkage state, hãy dùng loader mới trong phạm vi an toàn hoặc khởi chạy JVM mới, không gọi “clear cache” không tồn tại.

### 12.1. Một câu hỏi thiết kế trước khi dùng condy

Hãy tự hỏi: **“Giá trị này nên được chọn một lần cho mỗi defining class/run-time constant pool, hay nên được tính lại mỗi lần sử dụng?”**

- Nếu **chọn một lần**, condy phù hợp với mục tiêu biểu diễn constant resolution.
- Nếu **tính lại theo dữ liệu runtime**, một lời gọi method/factory hoặc target có logic động phù hợp hơn.
- Nếu **chọn một lần nhưng có thể fail tạm thời**, cần thiết kế failure policy và thời điểm khởi tạo rất cẩn thận, vì failed resolution không tự retry.

## 13. Bài tập tự kiểm tra và lời giải

**Câu 1.** Một class có hai lệnh `ldc #20` tham chiếu cùng `CONSTANT_Dynamic`. Lần đầu BSM trả `new String("A")`. Hai lệnh có buộc chạy BSM riêng không?  
**Đáp án:** Không. Khi entry đã resolve thành công, các lần dùng khác của cùng run-time constant-pool reference nhận cùng giá trị đã chọn.

**Câu 2.** Nếu đổi biến global từ `A` sang `B` sau khi `#20` resolve, lần `ldc #20` tiếp theo nhận gì?  
**Đáp án:** Vẫn giá trị `A` đã chọn nếu BSM không tự chạy lại; cache condy không theo dõi thay đổi biến global.

**Câu 3.** `ldc #20` và `ldc_w #20` có scope resolution khác nhau không?  
**Đáp án:** Không. Chúng chỉ khác độ rộng constant-pool index trong mã lệnh; cùng tham chiếu `#20` nghĩa là dùng cùng kết quả resolved.

**Câu 4.** Condy có descriptor `Ljava/lang/String;`, BSM trả null. Liên kết thất bại không?  
**Đáp án:** Không. Null có thể là một reference constant hợp lệ, và được cache.

**Câu 5.** Condy có descriptor `I`, BSM trả null. JVM báo gì?  
**Đáp án:** Conversion sang primitive `int` gây `NullPointerException`; resolution báo `BootstrapMethodError`. Ví dụ thực nghiệm xác nhận cause là NPE.

**Câu 6.** Condy `String` nhận `Integer.valueOf(7)` từ BSM. `ldc` có trả Integer rồi caller tự cast không?  
**Đáp án:** Không. Bootstrap result không đáp ứng field descriptor nên conversion bị `ClassCastException` và JVM báo `BootstrapMethodError` ở resolution.

**Câu 7.** BSM ném `IllegalStateException` lần đầu; caller đổi cờ rồi gọi method khác cũng dùng cùng `CONSTANT_Dynamic`. BSM chạy lại không?  
**Đáp án:** Không. Failed resolution của cùng entry được giữ lại. `fail` và `failAgain` trong thí nghiệm dùng chung một CP entry.

**Câu 8.** Một bootstrap trả `StringBuilder` mutable. Những `ldc` sau có nhận một StringBuilder mới không?  
**Đáp án:** Không do cache của cùng entry. Caller có thể quan sát trạng thái nội bộ bị thay đổi nếu object mutable và được chia sẻ.

**Câu 9.** Cùng classfile được định nghĩa bởi loader mới. Có thể nhận giá trị bootstrap mới không?  
**Đáp án:** Có. Class identity khác có run-time constant pool riêng. Đây không phải reset cache của class cũ.

**Câu 10.** BSM có thể chạy hai lần cạnh tranh lúc hai thread cùng resolve entry chưa có giá trị không?  
**Đáp án:** Có. JVMS cho phép bootstrap invocation cạnh tranh và chỉ chọn một kết quả để công bố, nên side effects của BSM phải thread-safe/idempotent khi cần.

**Câu 11.** Một `CONSTANT_Dynamic` kiểu `long` phải dùng `ldc_w` hay `ldc2_w`?  
**Đáp án:** `ldc2_w` với descriptor `J`; opcode khác không chỉ liên quan chỉ số lớn/nhỏ.

**Câu 12.** Một condy A dùng B làm static BSM argument, và B lại phụ thuộc A. JVMS xử lý thế nào?  
**Đáp án:** Resolution không hỗ trợ dependency cycle; việc phải resolve lại hằng đang được resolve dẫn tới `StackOverflowError`.

**Câu 13.** Vì sao không thể áp dụng quy tắc “hai instruction cùng constant-pool entry vẫn link riêng” của `invokedynamic` cho `ldc`?  
**Đáp án:** Vì `invokedynamic` cache CallSite riêng theo lexical instruction, còn `CONSTANT_Dynamic` cache giá trị theo run-time constant-pool symbolic reference.

**Câu 14.** Một BSM ném `AssertionError`. Có chắc `getCause()` của `BootstrapMethodError` sẽ là `AssertionError` không?  
**Đáp án:** Không. Theo JVMS, `Error` ném trực tiếp từ BSM có thể trở thành lỗi resolution mà không bắt buộc bị bọc vào BootstrapMethodError.

## 14. Tổng kết và tài liệu tham khảo

Cách ghi nhớ ngắn gọn:

```text
CONSTANT_Dynamic (field descriptor) + BootstrapMethods
                   |
                   v
      Resolve BSM + static arguments
                   |
                   v
      BSM(Lookup, name, Class<?>, ...)
                   |
                   v
      Chuyển kết quả sang declared type
          /                         \
      thành công                  thất bại
          |                         |
      cache VALUE               cache ERROR
          |                         |
ldc/ldc_w/ldc2_w              lần dùng lại
đều lấy VALUE                 không retry BSM
```

**Điểm cần nhớ:**

- `CONSTANT_Dynamic` chứa **symbolic recipe**, không phải kết quả thực tế trước khi resolve.
- `ldc`/`ldc_w` tải hằng không thuộc `long`/`double`; `ldc2_w` dùng cho `long`/`double`, kể cả condy tương ứng.
- Thành công: JVM **lưu giá trị đã chọn** theo run-time constant-pool entry và không gọi lại bootstrap cho những lần dùng sau.
- Thất bại: JVM giữ **lỗi resolution**; thử lại cùng entry không chạy bootstrap lần nữa.
- `null` hợp lệ đối với reference type nhưng không hợp lệ đối với primitive type.
- BSM trả object không đúng field descriptor gây `BootstrapMethodError` trong bước conversion.
- **Class loader mới** tạo class identity/constant pool mới; **concurrency** có thể tạo nhiều bootstrap executions cạnh tranh ở lần resolve đầu.
- Không nhầm cache của condy **theo entry** với `invokedynamic` **theo lexical instruction**.

**Tài liệu chính thức (Java 17):**

- [JVMS `5.4.3 Resolution và `5.4.3.6 Dynamically-Computed Constant and Call Site Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): thuật toán bootstrap, conversion, cache success/failure, concurrency và dependency cycle.
- [JVMS `4.4.10 `CONSTANT_Dynamic_info` và `CONSTANT_InvokeDynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): classfile format, tag `17`/`18` và field/method descriptors.
- [JVMS `6 `ldc`, `ldc_w`, `ldc2_w`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): operand widths, kiểu hằng và linking exceptions.
- [Oracle Java SE 17 — `BootstrapMethodError`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/BootstrapMethodError.html): ý nghĩa lỗi bootstrap cho dynamic constant và `invokedynamic`.
- [Oracle Java SE 17 — `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): những bootstrap methods có sẵn cho hằng động và các trường hợp sử dụng chuẩn.
- [Oracle Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): sử dụng `-c` để xem bytecode và `-v` để xem constant pool/BootstrapMethods.
