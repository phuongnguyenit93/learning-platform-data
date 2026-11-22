# Tạo stack map và giải quyết quan hệ kế thừa bằng ClassHierarchyResolver

Khi sinh hoặc biến đổi Java bytecode có nhánh điều kiện, vòng lặp và exception handler, JVM cần biết **kiểu xác minh (verification type)** của các giá trị trong *local-variable array* và *operand stack* tại những điểm điều khiển quan trọng. Thông tin này thường được mã hóa bằng thuộc tính `StackMapTable` của từng phương thức. Nếu thông tin sai, bytecode có thể không qua được bước xác minh và gây `VerifyError`, dù cú pháp của từng instruction trông có vẻ hợp lệ.

Với **Class-File API** chuẩn trong `java.lang.classfile` (chính thức từ **JDK 24**, theo JEP 484), trình dựng class file có thể tự sinh stack map. Việc tính frame đôi khi cần biết hai kiểu tham chiếu có chung lớp cha nào, một tên có phải interface không, hoặc kiểu nào tương thích với kiểu nào. **`ClassHierarchyResolver`** cung cấp dữ liệu phân cấp lớp cho việc sinh stack map và kiểm tra class file.

Bài học giải quyết năm vấn đề thực tế:

1. `StackMapTable` ghi gì và vì sao các nhánh điều khiển cần frame?
2. Class-File API sinh, tái sử dụng hoặc bỏ stack maps bằng tùy chọn nào?
3. `ClassHierarchyResolver` tra quan hệ cha/con từ đâu mà không bắt buộc đọc lớp qua system class loader?
4. Chọn resolver thế nào trong chương trình offline, ứng dụng nhiều class loader và Java agent?
5. Làm sao xác minh output bằng `javap`, `ClassFile.verify` và JVM thực, thay vì chỉ thấy hàm build trả về `byte[]`?

> **Ranh giới phiên bản:** `java.lang.classfile.ClassFile` và `java.lang.classfile.ClassHierarchyResolver` là API chuẩn từ **JDK 24**. Các ví dụ dùng chính hai API này bên dưới cần **JDK 24+** (lệnh hướng dẫn kiểm thử dùng **JDK 25**). Java 17–23 **không có cùng API chuẩn này**; bạn vẫn học/kiểm tra `StackMapTable` bằng `javac`, `javap` và JVM, nhưng không thể biên dịch `RebuildFrames.java` bằng `javac 17`. Đừng nhầm API chuẩn JDK 24 với các lần preview trước đó.

## 1. Stack map là thông tin cho verifier, không phải debug metadata

Trong JVM, một method có `Code` chứa instruction, `max_stack`, `max_locals`, exception handlers và các thuộc tính tùy chọn. `StackMapTable` là thuộc tính của `Code` phục vụ **verification by type checking**; nó không chứa giá trị object lúc chạy và không phải bảng dòng mã nguồn.

Một frame mô tả **type state** tại một bytecode offset:

```text
Frame tại bytecode offset X
  locals:
    slot 0 -> Integer
    slot 1 -> Object(java/lang/String)
    slot 2 -> Top / loại khác tùy trạng thái
  operand stack:
    entry 0 -> Object(java/lang/Number)
    ...
```

Đây là mô hình minh họa, không phải output chính xác của một method cụ thể. Các loại verification type gồm `Integer`, `Float`, `Long`, `Double`, `Null`, `Object`, `Top`, `UninitializedThis` và `Uninitialized`; cần phân biệt với tên/kiểu local trong `LocalVariableTable`.

| Cấu trúc | Mục đích | Có cần class hierarchy? |
|---|---|---|
| `Code` instructions | Chỉ dẫn JVM thực thi | Có thể cần hiểu kiểu để xác minh/biến đổi |
| `StackMapTable` | Khai báo type state ở các vị trí xác minh | **Có** khi gộp các kiểu tham chiếu từ các nhánh |
| `LocalVariableTable` | Tên, descriptor, slot và phạm vi biến để debug | Không dùng làm nguồn chân lý cho verifier |
| `LineNumberTable` | Liên hệ bytecode offset với số dòng nguồn | Không giải quyết quan hệ kế thừa |
| `ClassHierarchyResolver` | Cung cấp thông tin lớp cha/interface cho Class-File API | Chính là thành phần giúp suy luận quan hệ kiểu |

### 1.1. Các vị trí control-flow join quan trọng

```text
                 if (flag)
                 /      \
              nhánh A   nhánh B
              new Left  new Right
                  \      /
                   \    /
                    JOIN  <--- cần một verification type chấp nhận cả hai
                      |
                    tiếp tục
```

Nếu `Left extends Base` và `Right extends Base`, ở điểm hội tụ có thể dùng `Base` làm kiểu tham chiếu chung. Để tìm được thông tin này, công cụ phải biết:

```text
Left  -> superclass Base
Right -> superclass Base
Base  -> superclass java.lang.Object
```

Nếu resolver nhầm `Left` là subclass của kiểu khác, output có thể dùng một frame không tương thích; lỗi thường chỉ xuất hiện khi JVM xác minh lớp mới.

Không phải **mọi** instruction đều cần frame riêng. JVM Specification định nghĩa các điểm frame và cách nén (như `same_frame`, `append_frame`, `full_frame`). Frame ban đầu được suy từ descriptor của method và điều kiện đầu vào, không cần sao chép thủ công cho mọi vị trí bytecode.

### 1.2. `offset_delta` và đặc điểm của StackMapTable

`StackMapTable` mã hóa các frame theo thứ tự bytecode, sử dụng `offset_delta` để nén vị trí thay vì lặp lại BCI đầy đủ. Dạng frame cụ thể tùy trạng thái local/stack và tối ưu encoding của công cụ tạo class file.

- **BCI (bytecode index)** là offset trong `code[]` của **method hiện tại**, không phải số dòng nguồn.
- Với class file major version từ **50.0** trở lên, nếu không có `StackMapTable` thì JVMS định nghĩa một **implicit stack map** tương đương bảng có 0 entry. Điều này **không** có nghĩa một method có nhánh/handler tùy ý sẽ xác minh được nếu thiếu frame cần thiết.
- Một thuộc tính `StackMapTable` có tối đa một instance trong một `Code` attribute.
- Khi chèn/xóa instruction, bytecode offset, branch target, exception range, kiểu local/stack có thể đổi; vì vậy bản stack maps cũ có thể không còn dùng được.

Kết luận: **Stack map là chứng cứ kiểu cho verifier**, không phải dấu vết debug hay giá trị runtime.

## 2. Thí nghiệm nền tảng bằng Java 17+: xem một điểm hợp nhất kiểu

Tạo tệp **`MergeTarget.java`** dưới đây. Phần này dùng Java phổ thông, biên dịch/chạy được cả trên **JDK 17** lẫn **JDK 25**:

```java
class Base {
    String name() { return "base"; }
}

class Left extends Base {
    @Override String name() { return "left"; }
}

class Right extends Base {
    @Override String name() { return "right"; }
}

public final class MergeTarget {
    public static Base select(boolean left) {
        return left ? new Left() : new Right();
    }

    public static void main(String[] args) {
        System.out.println(select(true).name());
        System.out.println(select(false).name());
    }
}
```

Trong thư mục chứa file:

```shell
javac MergeTarget.java
java -Xverify:all MergeTarget
javap -v -p MergeTarget
```

**Stdout của chương trình:**

```text
left
right
```

Đầu ra `javap -v -p` khá dài. Tìm method `select(boolean)` và đoạn `StackMapTable` bên trong `Code`. Trên một bản OpenJDK/JDK 21 thông thường, có thể thấy phần tương tự:

```text
StackMapTable: number_of_entries = 2
  frame_type = 14 /* same */
  frame_type = 70 /* same_locals_1_stack_item */
    stack = [ class Base ]
```

Vị trí và encoding cụ thể là kết quả **phụ thuộc mã biên dịch/JDK**, không phải giá trị phải cố định trong mọi JDK. Nội dung quan trọng là frame ở nhánh hội tụ có thể biểu diễn **`Base`**, kiểu cha của `Left` và `Right`.

Câu lệnh `javap` chỉ **đọc class file được tạo**. Nó không tạo/chỉnh lại stack maps. Tùy chọn `java -Xverify:all` yêu cầu JVM thực hiện việc xác minh tích cực hơn; đây là bước kiểm tra runtime tốt sau khi chỉnh bytecode nhưng **không thay thế** kiểm tra đúng hành vi ứng dụng.

### 2.1. Tại sao có thể hiện `Base` trên stack?

Biểu thức điều kiện `left ? new Left() : new Right()` tạo hai đường đi. Sau nhánh, instruction tiếp theo cần thấy một type state chấp nhận được bất kể đường nào đã chạy. `Base` phù hợp vì cả hai đối tượng đều là instance của lớp con `Base`.

Hãy phân biệt:

- **Kiểu source/đích của method:** `Base` trong `public static Base select(...)`.
- **Kiểu kiểm chứng tại điểm hội tụ:** kiểu mà verifier chấp nhận trên operand stack, có thể xuất hiện trong `StackMapTable`.
- **Kiểu runtime thực:** `Left` hoặc `Right` tùy giá trị `left`; frame không hề lưu instance nào đã được tạo.

Một cách gỡ lỗi đơn giản là liên hệ lệnh tạo object, nhánh bytecode và frame trong `javap`, thay vì chỉ xem mã Java.

## 3. Class-File API và ba chế độ StackMapsOption

Khi viết hoặc transform `.class` bằng `ClassFile.of(...)`, bạn có thể chọn `ClassFile.StackMapsOption`:

| Tùy chọn | Hành vi | Khi nào dùng |
|---|---|---|
| `STACK_MAPS_WHEN_REQUIRED` | **Mặc định**: cố tái sử dụng stack maps cũ nếu code và exception handlers vẫn tương thích; nếu không thì sinh lại | Transform thông thường, muốn tránh tính lại không cần thiết |
| `GENERATE_STACK_MAPS` | **Luôn chạy sinh stack maps**, kể cả khi bản cũ có thể tái sử dụng; báo lỗi sớm nếu không sinh được | Kiểm thử resolver, muốn buộc tạo frame mới, thay đổi control flow |
| `DROP_STACK_MAPS` | **Không tự sinh** stack maps | Chỉ khi chủ động cung cấp `StackMapTableAttribute` tương thích hoặc có tình huống đặc biệt đã kiểm chứng |

Cú pháp thiết lập:

```java
ClassFile defaultContext = ClassFile.of();

ClassFile forced = ClassFile.of(
        ClassFile.StackMapsOption.GENERATE_STACK_MAPS
);
```

`ClassFile.of()` là một context cấu hình **đọc/ghi/generate** class file. `StackMapsOption` không phải tùy chọn của `javac` và không phải thuộc tính trong agent manifest.

### 3.1. Vì sao `DROP_STACK_MAPS` không phải cách sửa VerifyError?

Nếu code có nhánh hoặc exception handler đòi frame theo JVMS, bỏ `StackMapTable` có thể khiến class file không qua xác minh. `DROP_STACK_MAPS` chỉ phù hợp nếu bạn **tự đưa một `StackMapTableAttribute` hợp lệ vào `CodeBuilder`** hoặc có lý do đặc thù cho định dạng class. Đừng dùng “drop rồi JVM tự đoán” như giải pháp tổng quát trên class file hiện đại.

`StackMapTableAttribute` là **derived attribute** trong Class-File API: nó không xuất hiện như phần tử bình thường khi duyệt `CodeModel`. Thư viện thường quản lý nó khi ghi class file, trừ khi bạn dùng chế độ thủ công phù hợp.

### 3.2. Sinh frame có thể thất bại ngay khi viết

Tùy JVM/class version và bytecode, việc sinh stack map có thể ném `IllegalArgumentException`, ví dụ:

- **Unreachable code** xuất hiện sau một jump không điều kiện theo cách generation algorithm không chấp nhận.
- Bytecode dùng `jsr`/`ret` (legacy jump subroutine) không phù hợp với stack-map generation thông thường.
- Resolver không lấy được hierarchy info cần thiết hoặc gặp lớp không được phép truy vấn.
- Dữ liệu/nhãn/code model không hợp lệ hoặc các ràng buộc xây dựng class file không thỏa mãn.

Có `ClassFile.DeadCodeOption` để xử lý một số trường hợp dead code; không được diễn giải rằng mọi dead code đều có thể tự động biến thành bytecode hợp lệ. Thư viện tạo stack maps **không chứng minh logic nghiệp vụ** hoặc sự phù hợp với giới hạn redefine/retransform của JVM đang chạy.

## 4. `ClassHierarchyResolver` cung cấp thông tin gì?

Trong `java.lang.classfile`, `ClassHierarchyResolver` là **functional interface**; phương thức cốt lõi:

```java
ClassHierarchyResolver.ClassHierarchyInfo getClassInfo(
        java.lang.constant.ClassDesc classDesc);
```

Hàm nhận `ClassDesc` biểu diễn **một lớp hoặc interface**, và trả:

- `ClassHierarchyInfo.ofClass(superClassDesc)` nếu là class thông thường, khai báo **direct superclass**; với `java.lang.Object`, superclass có thể là `null`.
- `ClassHierarchyInfo.ofInterface()` nếu là interface.
- `null` nếu resolver **không biết** tên lớp đó (để resolver khác có cơ hội trả lời trong chuỗi `orElse`).
- `IllegalArgumentException` nếu lớp **không nên được truy vấn**, ví dụ không thể truy cập trong chính sách của resolver. Điều này **khác** với `null` và có thể khiến quá trình generation thất bại.

Thông tin trả về là metadata về hierarchy, **không** phải instance `Class<?>`, không phải bytecode thay thế, không chứa method body và không phải class loader. Nó hỗ trợ type analysis của Class-File API.

### 4.1. Các factory cần biết

| Factory/method | Nguồn metadata | Điểm mạnh | Rủi ro/giới hạn |
|---|---|---|---|
| `ClassHierarchyResolver.defaultResolver()` | Core reflection qua **system class loader** | Thuận tiện với lớp sẵn có trên system loader | Có thể làm load class; **không phù hợp** cho nhiều bối cảnh instrumentation |
| `ofClassLoading(ClassLoader)` | Load class qua loader và dùng reflection | Hiểu các lớp loader đó nhìn thấy | Có thể kích hoạt class loading khi chỉ đang muốn đọc metadata |
| `ofClassLoading(MethodHandles.Lookup)` | Reflection qua lookup có quyền truy cập phù hợp | Có ràng buộc accessibility rõ ràng | Lớp không truy cập được có thể gây `IllegalArgumentException` |
| `ofResourceParsing(ClassLoader)` | Đọc resource `.class` qua loader | Thường tránh load class chỉ để biết hierarchy | Resource có thể vắng mặt, không trùng lớp đã được define trong runtime |
| `ofResourceParsing(Function<ClassDesc, InputStream>)` | Ứng dụng tự cung cấp class bytes từ archive, repository, in-memory map… | Phù hợp offline/agent, kiểm soát nguồn bytes | Phải cung cấp đúng bytes/hierarchy, xử lý stream và lỗi I/O |
| `of(Collection<ClassDesc>, Map<ClassDesc, ClassDesc>)` | Danh sách interface + ánh xạ class → superclass | Nhỏ gọn, deterministic khi metadata đã biết | Không tự tìm thêm các tên thiếu trong map |
| `resolver.orElse(other)` | Resolver chính, fallback khi kết quả là `null` | Phối hợp metadata từ nhiều nguồn | Không “cứu” được `IllegalArgumentException` của resolver chính |
| `resolver.cached()` | Cache kết quả query, kể cả kết quả thiếu theo implementation | Giảm chi phí tra cứu lặp | Cache có thể stale; bản mặc định **không thread-safe** |

**Không nên tự gọi `getClassInfo` trong mã nghiệp vụ để “thử resolver”** như một API high-level: Javadoc nêu đây là phương thức Class-File API dùng để truy vấn; người dùng thường cấu hình resolver trong `ClassFile.ClassHierarchyResolverOption`. Nếu cần chẩn đoán, hãy kiểm thử đầu ra class-file và phần metadata nguồn của chính bạn.

### 4.2. Vì sao default resolver thường không đủ cho Java agent?

Javadoc chỉ rõ default resolver dùng reflection qua **system class loader**. Trong instrumentation:

1. Một lớp có thể do **custom class loader** định nghĩa (web container, plugin framework, application server).
2. Trong `transform(...)`, class mục tiêu có thể **đang được define**. Cố load class đó qua reflection ngay tại callback có thể gây tái nhập, tạo class-loading cycle, deadlock hoặc lấy phiên bản lớp không đúng.
3. Bytecode có thể chứa tham chiếu tới lớp vừa được sinh ra **chưa tồn tại trong JVM**.
4. Một class name không đủ phân biệt hai lớp cùng tên do hai defining class loader khác nhau.
5. System loader có thể không nhìn thấy resource trong nested JAR, module, custom resource store.

Vì vậy, chọn resolver có metadata **tương ứng đúng class-loader view và đúng phiên bản bytes**. Khi có nguồn `.class` phù hợp, `ofResourceParsing(...)` thường là lựa chọn an toàn hơn việc chủ động load class trong lúc transform.

### 4.3. Cách truyền resolver vào ClassFile context

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(
                ClassLoader.getSystemClassLoader());

ClassFile context = ClassFile.of(
        ClassFile.ClassHierarchyResolverOption.of(resolver),
        ClassFile.StackMapsOption.GENERATE_STACK_MAPS
);
```

Đây là đoạn cấu hình API **hợp lệ từ JDK 24+** nhưng chưa có các bước parse/transform; ví dụ chạy đầy đủ ở phần 5. `ClassFile.ClassHierarchyResolverOption.of(...)` khác với `ClassHierarchyResolver.of(...)`:

- `ClassHierarchyResolver.of(...)`: **tạo resolver từ metadata**.
- `ClassFile.ClassHierarchyResolverOption.of(resolver)`: **gắn resolver vào cấu hình** của quá trình parse/build/transform/verify.

Dùng nhầm hai tên `of` là lỗi biên dịch phổ biến khi mới học API.

## 5. Ví dụ JDK 25 chạy được: sinh lại StackMapTable với hierarchy metadata riêng

Ta dùng **`MergeTarget.java` ở phần 2**, giữ nguyên `Base`, `Left`, `Right` và method `select(boolean)`. Thêm file **`RebuildFrames.java`** dưới đây. Cách triển khai:

- Đọc class file cũ thành `ClassModel`.
- Cung cấp metadata trực tiếp cho các class local của ví dụ, để không phải dựa vào reflection khi giải quyết chúng.
- Sử dụng `ofResourceParsing` làm fallback cho các lớp JDK nếu cần.
- Buộc **tạo lại** stack maps bằng `GENERATE_STACK_MAPS` và ghi file sang thư mục `out`.
- Dùng `ClassFile.verify` cùng một resolver để phát hiện lỗi kiểm chứng, rồi kiểm tra bằng JVM.

### 5.1. `RebuildFrames.java`

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassHierarchyResolver;
import java.lang.classfile.ClassTransform;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;

public final class RebuildFrames {
    public static void main(String[] args) throws Exception {
        ClassDesc object = ClassDesc.of("java.lang.Object");
        ClassDesc base   = ClassDesc.of("Base");

        // Metadata biết trước: lớp nào có direct superclass nào?
        Map<ClassDesc, ClassDesc> parent = Map.of(
                base,                       object,
                ClassDesc.of("Left"),        base,
                ClassDesc.of("Right"),       base,
                ClassDesc.of("MergeTarget"), object
        );

        // Không có interface tự định nghĩa trong ví dụ này.
        ClassHierarchyResolver local =
                ClassHierarchyResolver.of(Set.of(), parent);

        // Chỉ hỏi fallback khi metadata local không có class cần tìm.
        ClassHierarchyResolver resolver = local.orElse(
                ClassHierarchyResolver.ofResourceParsing(
                        ClassLoader.getSystemClassLoader()));

        ClassFile cf = ClassFile.of(
                ClassFile.ClassHierarchyResolverOption.of(resolver),
                ClassFile.StackMapsOption.GENERATE_STACK_MAPS
        );

        byte[] original =
                Files.readAllBytes(Path.of("MergeTarget.class"));

        // Pass-through các ClassElement; force tái sinh stack maps
        // theo context đã cấu hình, không sửa method logic.
        byte[] rebuilt = cf.transformClass(
                cf.parse(original), ClassTransform.ACCEPT_ALL);

        Path output = Path.of("out", "MergeTarget.class");
        Files.createDirectories(output.getParent());
        Files.write(output, rebuilt);

        System.out.println("REBUILT");
        System.out.println("VERIFY_ERRORS=" + cf.verify(rebuilt).size());
    }
}
```

**Những dòng quan trọng:**

- `ClassDesc.of("Base")` là **descriptor của class trong default package**, không phải string dạng `LBase;` và không phải `Base.class`.
- `Map<ClassDesc, ClassDesc>` mô tả quan hệ **direct superclass**, không phải đồ thị đầy đủ của các method.
- `ClassHierarchyResolver.of(Set.of(), parent)` tạo resolver từ metadata. Danh sách interface trống là đúng cho đúng **bốn class do thí nghiệm định nghĩa**, không có nghĩa JDK không có interface.
- `local.orElse(...)` cho resolver khác trả lời nếu metadata local thiếu. Resolver chính trả `null` mới thử fallback.
- `ClassTransform.ACCEPT_ALL` chuyển toàn bộ các class elements sang builder; option `GENERATE_STACK_MAPS` khiến builder không chỉ sao chép bảng frame cũ nếu việc sinh được yêu cầu.
- `Files.write` vào `out/MergeTarget.class` **không sửa đè** bản `MergeTarget.class` đầu vào. Các class `Base`/`Left`/`Right` gốc vẫn nằm ở thư mục hiện tại.
- `cf.verify(rebuilt)` trả danh sách `VerifyError` của Class-File API; `size()==0` là kết quả mong đợi trong ví dụ hợp lệ, nhưng còn cần kiểm tra bằng JVM thực.

### 5.2. Lệnh biên dịch và chạy

**Dùng JDK 25** cho cả `javac` và `java` ở bước Class-File API; kiểm tra `java -version` và `javac -version` nếu có nhiều JDK.

```shell
javac MergeTarget.java RebuildFrames.java
java RebuildFrames
javap -v -p -classpath out MergeTarget
java -Xverify:all -cp out:. MergeTarget
```

Lệnh `javac` đặt `MergeTarget.class`, `Base.class`, `Left.class`, `Right.class` và `RebuildFrames.class` trong thư mục hiện tại. `java RebuildFrames` tạo `out/MergeTarget.class`.

**Stdout mong đợi khi `RebuildFrames` hoàn thành và resolver có đầy đủ metadata:**

```text
REBUILT
VERIFY_ERRORS=0
```

Trong output `javap`, tìm `select(boolean)` và `StackMapTable`; số entry và encoding có thể khác giữa các bản JDK/kiểu transform. Vì `-classpath out` chỉ định đường dẫn chứa class được rebuild, `javap` đang đọc output, **không** nhầm sang bản input ở thư mục hiện tại.

Cuối cùng, `java -Xverify:all -cp out:. MergeTarget` **ưu tiên thư mục `out`**, trong khi vẫn tìm được `Base`/`Left`/`Right` tại `.`. Stdout kỳ vọng:

```text
left
right
```

Đây là điều kiện hậu kiểm quan trọng: JVM có thể load/verify class mới và logic phân nhánh cho ra kết quả như trước.

**Phạm vi QA:** ví dụ sử dụng method, option và factory trong API chính thức của **JDK 25**. Kết quả `StackMapTable` cụ thể do `javap` in ra phụ thuộc class file đã biên dịch và phiên bản JDK, do đó không nên kiểm tra bằng so khớp nguyên văn số frame/BCI. Nếu chạy bằng JDK 17 hoặc 21, `RebuildFrames.java` sẽ không biên dịch vì `java.lang.classfile` chưa có ở những bản đó.

### 5.3. Điều gì thực sự chứng minh resolver hoạt động?

Trong ví dụ, phép tạo class và `cf.verify(...)` hoàn tất xác nhận **một bộ dữ liệu hierarchy đủ dùng cho lượt xử lý này**. Nhưng không nên kết luận API đã thực sự gọi `getClassInfo` trên *từng* tên bạn đưa vào map; thuật toán có thể chỉ truy vấn các kiểu cần thiết.

Nếu cần đo đúng những tên đã tra cứu trong một agent nghiên cứu, hãy cung cấp một `ClassHierarchyResolver` tùy chỉnh có logging/metrics an toàn và gắn vào `ClassHierarchyResolverOption`. Tránh log từ bên trong resolver bằng code gây thêm class loading trong production.

## 6. Hiểu sâu phương thức getClassInfo và ClassHierarchyInfo

### 6.1. “Không biết” khác “không cho hỏi”

Hai kết quả thường bị đánh đồng:

```text
getClassInfo(classDesc) trả null
  -> resolver không có metadata
  -> resolver.orElse(...) có thể dùng nguồn thứ hai

getClassInfo(classDesc) ném IllegalArgumentException
  -> loại truy vấn bị từ chối/không hợp lệ theo hợp đồng resolver
  -> không được giả định orElse(...) sẽ tiếp tục
```

Khi viết resolver tùy chỉnh, chỉ trả `null` nếu đúng là **không biết**. Nếu bạn biết truy vấn không được phép hoặc metadata chắc chắn không đáng tin, có thể báo lỗi rõ ràng theo chính sách. Đừng trả thông tin cha giả để “đi vòng” lỗi.

### 6.2. Các kiểu thông tin hợp lệ

```java
// Hai biểu thức API minh họa (JDK 24+):
var declaredClass =
    ClassHierarchyResolver.ClassHierarchyInfo.ofClass(
        ClassDesc.of("java.lang.Object"));

var declaredInterface =
    ClassHierarchyResolver.ClassHierarchyInfo.ofInterface();
```

Đoạn mã **minh họa** này giả định có import `java.lang.constant.ClassDesc` và `java.lang.classfile.ClassHierarchyResolver`. Với một class con cụ thể, `ofClass(...)` nhận descriptor của **lớp cha trực tiếp**. Với interface, `ofInterface()` thể hiện nó là interface theo hợp đồng resolver; không tự suy đây là class có superclass tùy ý.

Đừng tự động coi `null` từ `ClassHierarchyInfo.ofClass(null)` cho **mọi** class chưa biết là hợp lệ; `null` superclass chỉ thích hợp khi không có superclass theo định nghĩa, điển hình là `java.lang.Object`. Đối với một class thông thường, metadata giả sẽ dẫn đến phân tích type state sai.

### 6.3. Resolver có nắm đủ quan hệ interface không?

API lưu thông tin “đây là interface” và superclass cho class; việc phân tích quan hệ verification type theo JVMS **không giống** việc xây một sơ đồ đầy đủ mọi interface/triển khai/method. Khi chọn metadata, hãy theo đúng dữ liệu mà `ClassHierarchyResolver` yêu cầu thay vì giả định nó là một thay thế hoàn chỉnh cho reflection/class graph.

Với `Left` và `Right` đều kế thừa `Base` như ví dụ, thông tin superclass là phần cốt lõi. Khi bytecode dùng interface, array hoặc nhiều tầng class loader, resolver còn phải có đủ thông tin cho **mọi kiểu tham chiếu mà generator cần truy vấn**; không nên suy một kiểu từ tên package hay áp đặt `java.lang.Object` cho tất cả.

### 6.4. Resolver thiếu một kiểu chỉ khi chạy trên dữ liệu khó?

Một generator có thể chỉ cần hierarchy khi gặp nhánh có hai reference types khác nhau. Trong method tuyến tính, công cụ có thể không phải truy vấn resolver cho một lớp tùy chỉnh. Vì vậy resolver bị thiếu dữ liệu có thể **ẩn lỗi** cho đến khi bạn biến đổi:

- biểu thức điều kiện;
- vòng lặp với reference variable;
- `try/catch` và exceptional control-flow edges;
- nhánh gọi phương thức cùng trả về các kiểu con khác nhau;
- method có array/component reference types;
- code được chèn làm thay đổi chiều cao/kiểu operand stack.

Không dùng “đã transform một class đơn giản thành công” làm bằng chứng resolver đủ dùng cho toàn bộ ứng dụng.

## 7. Resolver trong agent: vì sao tránh loading class khi đang transform?

Java agent thông qua `java.lang.instrument.ClassFileTransformer` nhận byte array của lớp đang nạp hoặc đang redefine/retransform:

```java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {
    // Đoạn mô tả bối cảnh callback, chưa là agent độc lập.
    return null;
}
```

Nếu agent sử dụng Class-File API **bên trong** callback này, `ClassHierarchyResolver.defaultResolver()` có thể truy vấn qua system class loader và gây loading lớp mới. Trong thời điểm target class có thể chưa hoàn tất quá trình define, điều này không an toàn để mặc định làm.

Chiến lược thiết kế:

1. Xác định **loader của target** từ tham số `loader` (có thể `null` cho bootstrap loader). Đừng áp một resolver từ app loader khác chỉ vì class có cùng binary name.
2. Ưu tiên metadata từ **bytes/class resources đã được phép đọc** thay vì kích hoạt việc tải lớp để tìm `getSuperclass()`.
3. Nếu lớp mục tiêu đang được define mà chưa có resource chính xác, cung cấp metadata của **chính class bytes đang transform** hoặc kho class bytes đã chụp đúng build/loader; không buộc system loader load lại target.
4. Chọn `ofResourceParsing(loader)` khi resource lookup phản ánh đúng loader; với classloader có `defineClass(byte[])` từ network/cache mà không công bố resource, dùng `ofResourceParsing(Function<ClassDesc,InputStream>)` và cung cấp bytecode từ nguồn đúng.
5. Với class JDK/boot classes, dùng resolver được cấu hình có thể tìm đúng metadata module/runtime. Không giả định loader null có cùng resource behavior với system loader.
6. Đặt phạm vi **cache theo class loader + phiên bản build/bytes** nếu metadata có thể thay đổi; `ClassDesc` đơn lẻ không biểu diễn defining loader.

### 7.1. Gắn resolver vào context trong callback

Ví dụ cấu hình rút gọn:

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(loader);

ClassFile cf = ClassFile.of(
        ClassFile.ClassHierarchyResolverOption.of(resolver),
        ClassFile.StackMapsOption.STACK_MAPS_WHEN_REQUIRED
);
```

Đây là **mẫu kiến trúc**, không phải một callback hoàn chỉnh: `loader` có thể `null`; class loader có thể không cung cấp resource cho chính target đang xử lý; và transformer còn cần quy tắc filter, lỗi, bytecode generation, không recurse vào chính dependency của agent.

Không máy móc gọi `ofResourceParsing(loader)` trong mọi tình huống mà không xét thiết kế loader và nguồn class bytes. Đối với trường hợp khó, hãy dùng resolver kết hợp metadata **có độ tin cậy cao** với một fallback phù hợp.

### 7.2. Tránh cache toàn cục sai theo class name

Ví dụ hai plugin loader:

```text
loader-A:
  com.example.PluginType extends com.example.BaseA

loader-B:
  com.example.PluginType extends com.example.BaseB
```

Cùng một `ClassDesc.of("com.example.PluginType")`, nhưng hai định nghĩa lớp khác nhau. Nếu cache thông tin `PluginType → BaseA` rồi dùng để tạo frames cho class do loader-B định nghĩa, bạn đã chọn sai hierarchy. Có thể tạo class bytes sai verification types ngay cả khi tên class trông đúng.

Thực tiễn an toàn:

- Resolver/cache gắn với loader và artifact/class version phù hợp.
- Không chia sẻ một map tên → superclass toàn JVM trừ khi các tên đó thật sự là cùng không gian lớp được quản lý.
- Không giữ cache vô hạn nếu class loader có thể unload; tránh giữ reference mạnh tới loader mà không cần thiết.
- Dùng `cached()` có ý thức: mặc định không thread-safe; kết quả `null` cũng được cache theo hợp đồng; dữ liệu thay đổi sau đó không tự cập nhật.
- Nếu cần concurrency, cân nhắc `cached(Supplier<Map<...>> cacheFactory)` với map thread-safe được chọn cẩn thận, đồng thời hiểu yêu cầu hỗ trợ các giá trị `null`. Không tùy tiện dùng `ConcurrentHashMap` nếu implementation cache cần lưu `null`.

## 8. So sánh resolver reflection và resource parsing

| Câu hỏi | `ofClassLoading(...)` | `ofResourceParsing(...)` |
|---|---|---|
| Tra hierarchy bằng cách nào? | Nhờ class loading và reflection | Đọc class file resource hoặc InputStream do ứng dụng cung cấp |
| Nguy cơ làm phát sinh class loading? | **Có**; đặc biệt đáng chú ý trong agent | Tránh load class chỉ để tra metadata, nhưng resource lookup/I/O vẫn có tác dụng phụ |
| Phụ thuộc tính khả kiến của loader? | Có | Có, hoặc phụ thuộc function cung cấp stream |
| Phù hợp class chưa được define? | Không nên tự giả định có thể load an toàn | Có thể phù hợp nếu có đúng bytes từ build/cache/transform context |
| Phù hợp class trong JAR hoặc module? | Khi loader/lookup có thể thấy | Khi resolver tìm được đúng class-file resource |
| Cần kiểm soát resource lifecycle? | Do class loading/reflection xử lý | Có thể cần quản lý streams và lỗi I/O trong function |
| Dữ liệu có thể stale? | Có, nếu dùng loader/lookup sai | Có, nếu resource trên đĩa khác phiên bản class đã nạp |

**Ưu tiên trong instrumentation:** đừng để việc *tính stack map* vô tình kích hoạt một đợt class loading mới vào đúng lúc hệ thống đang load class. Resolver dựa trên bytes có thể là công cụ phù hợp hơn, nhưng vẫn phải xem hiệu năng, classloader và giới hạn I/O.

## 9. Khi nào cần tự sinh stack maps, khi nào chỉ cần tái sử dụng?

### 9.1. Thay đổi nhỏ không ảnh hưởng instruction/control-flow

Ví dụ đổi một attribute độc lập của class, không sửa method `Code`. Nếu builder xác định stack maps cũ còn tương thích, **`STACK_MAPS_WHEN_REQUIRED`** có thể tái sử dụng. Dùng `GENERATE_STACK_MAPS` vẫn hợp lệ nhưng thêm chi phí và có thể phát hiện vấn đề hierarchy vốn không cần nếu reuse.

### 9.2. Chèn probe vào method body

Nếu chèn instructions mới ở đầu/giữa method, làm thay đổi offset, locals, operand stack hoặc exception handler, stack maps cũ có thể không còn phù hợp. Class-File API có thể tái tạo frame khi cần, nhưng phải có hierarchy đủ chính xác để giải quyết merge. Không nên tự copy bảng `StackMapTable` cũ qua output chỉ vì hai method có cùng tên.

### 9.3. Tái tạo toàn bộ method với control-flow mới

Với code mới, đặc biệt có branch/handler, thường cần **generation** mới. Bật `GENERATE_STACK_MAPS` là cách trực tiếp để kiểm thử đường tạo frames và resolver. Dù vậy, vẫn phải đảm bảo bytecode **stack discipline**, kiểu return, branch targets, handler ranges và giới hạn class-file version hợp lệ.

### 9.4. Tạo frame thủ công

Các trường hợp hiếm muốn kiểm soát từng frame có thể dựng `StackMapTableAttribute` bằng API nâng cao và dùng `DROP_STACK_MAPS` để ngăn generator ghi đè. Đây là nhiệm vụ đòi hiểu `StackMapFrameInfo`, label và offset; thiếu frame ở nhánh hoặc handler thường dẫn tới `VerifyError`. Nếu không có lý do rất rõ, hãy dùng generation tự động và resolver đúng.

## 10. Lỗi thường gặp: nguyên nhân và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Việc nên làm |
|---|---|---|
| `javac` báo không tìm thấy `java.lang.classfile` | Đang dùng JDK 17–23 thay vì JDK 24+ | Kiểm tra `javac -version`; dùng JDK 25 cho ví dụ |
| `transformClass` ném `IllegalArgumentException` lúc tạo stack maps | Thiếu hierarchy info, truy vấn bị từ chối, dead code, legacy `jsr/ret` hoặc class-file inconsistency | Ghi cause, xác định class/loader, kiểm tra bytes/option/resolver |
| `VerifyError: Inconsistent stackmap frames` | Frame local/operand stack không tương thích với bytecode tại branch/handler | Dùng `javap -v` xem BCI/frames; thử generation đúng hierarchy; chạy `-Xverify:all` |
| `NoClassDefFoundError` khi resolver cố load lớp | Class chưa có/loader sai/quá trình load phụ thuộc vòng | Tránh reflection-based loader trong callback, dùng resource/class bytes đúng |
| Generation “thành công” nhưng JVM từ chối lớp | Resolver trả hierarchy giả, version/method constraints hoặc bytecode cuối không hợp lệ | Kiểm bằng JVM thực, so bytes/class version và loader |
| Dùng `defaultResolver()` trong custom-loader app | System loader không biết type từ plugin loader | Dùng resolver scoped theo loader hoặc repository/bytes của plugin |
| Cache cho kết quả sai giữa hai lần deploy | Dữ liệu metadata đã đổi nhưng resolver cached | Định phạm vi cache theo build/loader, invalidate theo lifecycle |
| `DROP_STACK_MAPS` để “sửa” stack map error | Thiếu frames mà verifier cần | Dùng generation/frames hợp lệ, đừng xóa để né lỗi |
| `StackMapTable` không hiện khi duyệt `CodeModel` | Attribute là derived property, không được giao như element thường | Xem `StackMapTableAttribute`, `javap -v`, và option sinh maps |
| `cf.verify(bytes).size()==0` nhưng app lỗi logic | Verifier kiểm kiểu/class-file constraints, **không** chứng minh nghiệp vụ | Viết thêm tests và chạy mã thực |
| Agent bị deadlock/tái nhập khi transform | Resolver dùng class loading/reflection hoặc logging nặng trong callback | Chuyển sang metadata offline/resource, giảm phụ thuộc trong callback |
| Output class chạy bản cũ | Classpath ưu tiên sai, build artifacts lẫn nhau | Kiểm `-cp out:.`, đường dẫn `javap` và hash/phiên bản class bytes |

### Quy trình debug có thứ tự

1. Ghi **JDK version của công cụ**, major version của input `.class`, loader và nguồn class bytes.
2. Xác nhận `ClassFile.StackMapsOption` thực sự dùng: default hay bắt buộc regenerate.
3. Xem **đúng** output bytes với `javap -v` để thấy stack frames và branch targets.
4. Khi generation lỗi, xác nhận resolver biết tất cả type quan trọng ở nhánh hợp nhất, superclass/interface và array components.
5. Với runtime agent, bảo đảm dữ liệu resolver khớp **defining loader** của target, không chỉ system loader.
6. Dùng `ClassFile.verify` để có danh sách lỗi, rồi chạy JVM với `-Xverify:all` và test hành vi.
7. Chỉ báo thành công khi **class bytes được JVM chấp nhận và chức năng mong muốn vẫn chạy**.

## 11. Những hiểu nhầm cần tránh

1. **“Đã có StackMapTable thì không cần quan hệ kế thừa.”** Sai khi code bị transform làm mất tính tương thích của frames cũ; generator cần hierarchy chính xác.
2. **“`ClassHierarchyResolver` tự động load đúng mọi class.”** Sai. Tùy resolver factory, loader, resource và visibility; default dùng system loader qua reflection.
3. **“`ClassDesc` đại diện luôn cho defining class loader.”** Sai. Nó mô tả type symbol, không phân biệt hai định nghĩa cùng binary name ở loader khác nhau.
4. **“`ofResourceParsing` chắc chắn nhìn thấy class do custom loader define.”** Sai nếu loader không công bố resource tương ứng.
5. **“Cứ thiếu superclass thì trả `java.lang.Object`.”** Có thể tạo kết quả không chính xác; đừng giả hierarchy để ép generator chạy.
6. **“Bật `GENERATE_STACK_MAPS` là bytecode tự động hợp lệ.”** Sai. Nó có thể ném lỗi; code còn phải thỏa các quy tắc verifier khác.
7. **“`DROP_STACK_MAPS` tương đương nhờ JVM suy type lại.”** Sai như một chiến lược chung cho class file hiện đại.
8. **“`StackMapTable` là bảng local variable debug.”** Sai; hai attribute giải quyết hai bài toán khác nhau.
9. **“`cached()` luôn thread-safe.”** Sai; factory mặc định dùng map không thread-safe.
10. **“Một class build thành công chứng minh resolver đủ dữ liệu cho mọi branch.”** Sai; chỉ các type thực tế được generator truy vấn mới bộc lộ thiếu dữ liệu.
11. **“Stack maps là con trỏ tới object đang chạy.”** Sai; chúng mang verification types, không mang runtime values.
12. **“JDK 17 có sẵn cùng `Class-File API` chuẩn.”** Sai; các lớp trong ví dụ `RebuildFrames` cần JDK 24+.

## 12. Câu hỏi tự kiểm tra

1. **`StackMapTable` phục vụ gì?** Cung cấp type states cho verifier của JVM tại các vị trí điều khiển quan trọng.
2. **Giả sử `Left extends Base` và `Right extends Base`. Khi hai nhánh hợp nhất, vì sao cần hierarchy?** Vì generator cần một verification type tương thích với giá trị đến từ cả hai nhánh, điển hình là `Base`.
3. **`GENERATE_STACK_MAPS` khác `STACK_MAPS_WHEN_REQUIRED` thế nào?** Một bên buộc sinh lại, bên kia có thể tái sử dụng stack maps cũ nếu còn tương thích.
4. **`DROP_STACK_MAPS` có tự giải quyết nhánh thiếu frame không?** Không. Nếu code cần frame, người viết phải cung cấp frame hợp lệ.
5. **`ClassHierarchyResolver.defaultResolver()` dùng nguồn gì?** Reflection qua system class loader; có rủi ro class loading và không thấy custom-loader types.
6. **`ClassHierarchyResolver.ofResourceParsing(...)` có gọi `Class.forName` cho mỗi tên không?** Không có hợp đồng như vậy; nó lấy hierarchy từ class-file resources/streams thay vì chủ động dùng reflection-based class loading.
7. **`getClassInfo(...)` trả `null` có khác ném `IllegalArgumentException` không?** Có. `null` là không biết, còn exception có thể báo truy vấn không được phép và chặn generation.
8. **Tại sao map theo `ClassDesc` không nên dùng chung mọi class loader?** Vì cùng tên type có thể có superclass khác nhau theo defining loader.
9. **`ClassFile.verify(rebuilt).size()==0` có đủ để công bố business logic đúng không?** Không. Cần JVM verification và tests hành vi.
10. **Tại sao không nên dùng reflection resolver trong transformer của class đang được define?** Có nguy cơ làm phát sinh class loading, tái nhập hoặc vòng phụ thuộc ngay trong quá trình load.
11. **Vì sao `javap -v` vẫn dùng tốt trên Java 17 dù Class-File API chuẩn yêu cầu JDK 24+?** `javap` là công cụ đọc class file, còn `java.lang.classfile` là API lập trình được chuẩn hóa sau này.
12. **Nếu `StackMapTable` cũ được giữ nhưng instruction offset thay đổi, có thể xảy ra gì?** Frame không còn khớp BCI/type state, có thể bị verifier từ chối với `VerifyError`.
13. **Lúc nào custom resolver dạng `of(Collection, Map)` thích hợp?** Khi đã có metadata đáng tin cậy (ví dụ build index hoặc class bytes của module), muốn tránh class loading để lấy quan hệ cha/interface.
14. **Nếu resolver không có metadata cho lớp mới được sinh trong pipeline, nên làm gì?** Bổ sung hierarchy thật từ bytes đang sinh/repository, hoặc báo lỗi rõ; không bịa lớp cha.

## 13. Tài liệu chính thức để tra cứu

- [OpenJDK JEP 484 — Class-File API](https://openjdk.org/jeps/484): API chuẩn từ JDK 24; bối cảnh thay thế việc sử dụng API bytecode nội bộ.
- [Java SE 25 — Class-File API package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/package-summary.html): cách đọc, sinh và biến đổi class file; models, transforms, attributes.
- [Java SE 25 — ClassHierarchyResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassHierarchyResolver.html): `getClassInfo`, `defaultResolver`, `ofResourceParsing`, `ofClassLoading`, `orElse` và `cached`.
- [Java SE 25 — ClassFile.ClassHierarchyResolverOption](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.ClassHierarchyResolverOption.html): gắn resolver vào context khi generate/verify.
- [Java SE 25 — ClassFile.StackMapsOption](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.StackMapsOption.html): `STACK_MAPS_WHEN_REQUIRED`, `GENERATE_STACK_MAPS`, `DROP_STACK_MAPS`.
- [Java SE 25 — StackMapTableAttribute](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/attribute/StackMapTableAttribute.html): thuộc tính derived, cách sinh hoặc tự cung cấp.
- [Java SE 25 — ClassTransform](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassTransform.html): `ACCEPT_ALL` và cách chuyển tiếp class elements khi transform.
- [Java SE 25 JVM Specification, `4.7.4 và `4.10.1](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): định nghĩa `StackMapTable`, frame offsets, verification type system.

**Ghi nhớ:** `StackMapTable` là dữ liệu xác minh type state, còn `ClassHierarchyResolver` là nguồn metadata để Class-File API suy ra quan hệ kế thừa khi sinh/kiểm tra frame. Trong agent, chọn resolver nhìn đúng **class bytes, class loader và phiên bản build**, tránh gây class loading không cần thiết; sau khi sinh luôn kiểm tra **class file lẫn hành vi JVM thực**.