# Class-File API: model bất biến, phân tích trì hoãn và lưu ý khi chia sẻ giữa các luồng

## 1. Vấn đề cốt lõi

**Class-File API** chuẩn trong `java.lang.classfile` cho phép đọc, tạo và biến đổi nội dung tệp `.class`. API được chuẩn hóa từ **JDK 24** (JEP 484); ở JDK 22–23 nó từng là tính năng preview. Bài này xét ba tính chất liên hệ chặt chẽ:

1. **Model bất biến:** `ClassModel`, `MethodModel`, `FieldModel`, `CodeModel` và các element mô tả class file ở dạng không có thao tác sửa trực tiếp. Muốn thay class file, ta dùng builder/transform để sinh bytes mới.
2. **Phân tích trì hoãn (lazy parsing/inflation):** sau `ClassFile.of().parse(bytes)`, không nhất thiết mọi method body, attribute, instruction và constant-pool entry đều được giải mã. Những phần này có thể được tạo khi accessor được gọi.
3. **An toàn đa luồng phải được xem xét riêng:** dù giao diện model bất biến, tài liệu Java 24 ghi rõ **model có thể không thread-safe do tính lười**. Một accessor đọc có thể làm thư viện khởi tạo hoặc cache cấu trúc nội bộ.

Vì thế câu “`ClassModel` là immutable, chắc chắn cho nhiều thread dùng chung không khóa được” **không đúng theo hợp đồng API**. Một model chỉ để đọc không đồng nghĩa đã được vật chất hóa hoàn toàn, cũng không đồng nghĩa có bảo đảm đồng bộ cho các cấu trúc được dựng khi cần.

Tài liệu chính thức: [java.lang.classfile — Reading classfiles, Models and elements](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html).

## 2. Mô hình cây: đọc đúng phần cần thiết

~~~text
byte[] chứa class file
         |
         v
ClassFile.of().parse(bytes)
         |
         v
ClassModel
  |-- thisClass(), flags(), interfaces(), majorVersion()
  |-- fields()          -> FieldModel -> metadata/attributes
  |-- methods()         -> MethodModel -> methodName(), methodType()
  |                                       |
  |                                       +-- code() -> Optional<CodeModel>
  |                                                         |
  |                                                         +-- code elements
  |-- attributes()      -> class attributes
  +-- constantPool()    -> read-only constant pool / PoolEntry
~~~

Một `MethodModel` có thể được truy cập qua `ClassModel.methods()` hoặc xuất hiện như một `ClassElement` khi duyệt `ClassModel`. Một `CodeModel` là model con của method và chứa instruction, label, metadata liên quan. API cung cấp cả **random access** lẫn cách duyệt `Iterable`/`elementStream()`.

Nếu chỉ lập danh sách tên method, truy cập `methods()` và `methodName()` là đủ; không cần đi sâu từng `CodeModel`. Nếu phân tích lời gọi method, field access hoặc branch, mới cần đi vào phần code.

~~~java
ClassModel model = ClassFile.of().parse(bytes);
for (MethodModel method : model.methods()) {
    System.out.println(method.methodName().stringValue());
}
~~~

Đây là **mảnh mã JDK 24+** trong một chương trình có `byte[] bytes` và import `ClassFile`, `ClassModel`, `MethodModel`. Nó minh họa cách đọc metadata; không phải chương trình độc lập.

**`ClassModel` khác `Class<?>`:** model mô tả bytes theo định dạng JVM class file; `java.lang.Class` đại diện kiểu đã được class loader định nghĩa trong JVM. `ClassFile.parse` không tương đương `Class.forName` và không yêu cầu chạy static initializer của lớp đang đọc. Sự phân biệt này quan trọng khi dùng API trong Java agent vì ta thường muốn phân tích class bytes mà không gây class loading mới.

## 3. Bất biến có ý nghĩa gì?

Một model đã parse cung cấp *mô tả logic* về class file. Không có thao tác như `model.methods().get(0).setName("changed")` để sửa class gốc; phương thức kiểu đó không thuộc API.

Để thay nội dung, quy trình là:

~~~text
class bytes gốc -> parse -> ClassModel bất biến
                              |
                              v
                     ClassTransform/builder
                              |
                              v
                       byte[] đầu ra mới
                              |
                              v
                      parse -> model mới
~~~

Ví dụ mảnh code minh họa, với `sourceBytes` đã có:

~~~java
ClassFile context = ClassFile.of();
ClassModel original = context.parse(sourceBytes);

byte[] rewritten = context.transformClass(
        original, (builder, element) -> builder.with(element));

ClassModel after = context.parse(rewritten);
~~~

`transformClass` tạo bytes đầu ra, còn `original` không bị sửa. Transform trên chỉ chuyển tiếp các element để giải thích hướng xử lý; không hứa mảng bytes đầu ra giống nguyên từng byte với đầu vào. Những builder có trạng thái dùng trong quá trình xuất bytes mới **không được mặc nhiên coi là thread-safe**.

Bất biến ở đây **không** tự kéo theo các kết luận sau:

- **Không có công việc nội bộ:** accessor có thể giải mã/cấp phát/cache cấu trúc mới vì lazy parsing.
- **Đầu vào không thể sửa:** `byte[]` vẫn là mảng Java có thể bị caller khác ghi; chủ sở hữu phải giữ nguyên hoặc sao chép nó.
- **Mọi object con đều an toàn dùng chung:** `MethodModel`/`CodeModel` cũng có thể được inflate lười.
- **Có thể share builder:** builder phục vụ quá trình xây class file; dùng builder riêng theo tác vụ.

Ví dụ một `List<MethodModel>` tuy được bọc bằng `List.copyOf` vẫn chứa **các model lazy**. Danh sách không cho thêm/xóa phần tử nhưng những model bên trong chưa vì thế trở thành thread-safe. Muốn chia sẻ kết quả, hãy trích `String`, số nguyên, enum hoặc DTO bất biến thực sự.

## 4. Lazy parsing giúp tiết kiệm gì?

Class file có thể chứa nhiều method body, metadata debug, annotation, stack map, bootstrap method, constant-pool entry. Không phải công cụ nào cũng cần đọc tất cả.

| Công việc | Mức thông tin cần |
| --- | --- |
| In tên class, phiên bản class file | `thisClass()`, `majorVersion()` |
| Liệt kê method/field | `methods()`, `fields()` và các accessor tên/descriptor |
| Đọc annotation | Các attribute hoặc phần tử annotation tương ứng |
| Phân tích bytecode gọi method/đọc field | `method.code()` rồi duyệt `CodeElement` |
| Viết lại class | Parse model, tạo builder/transform, xuất bytes và kiểm tra |
| Quét hàng nghìn class | Chỉ truy vấn thông tin cần trước, phân tích sâu theo nhu cầu |

Không nên giả định chính xác mức cấp phát của một accessor; đó là chi tiết triển khai. Hợp đồng quan trọng là **thông tin có thể được phân tích muộn**, nên việc parse nhanh không chứng minh toàn bộ cây đã sẵn sàng.

Đoạn sau đi sâu hơn, khi thực sự cần đọc code:

~~~java
for (MethodModel method : model.methods()) {
    method.code().ifPresent(code -> {
        for (CodeElement element : code) {
            // Chỉ phân tích phần tử code liên quan đến mục tiêu.
        }
    });
}
~~~

Đây cũng là **mảnh mã trong ngữ cảnh đã có `model` và import `CodeElement`**. `method.code()` trả `Optional<CodeModel>` vì method `abstract`/`native` có thể không có phần code. Các code element có thể gồm instruction lẫn metadata/label, không nên đếm mọi element là một instruction.

## 5. Lazy parsing làm thay đổi cách xử lý lỗi

Theo Javadoc, `ClassFile.parse(byte[])` có thể ném `IllegalArgumentException` với bytes không hợp lệ hoặc class-file version không hỗ trợ. **Do parsing theo nhu cầu**, lỗi tương tự cũng có thể xuất hiện **sau khi `parse` đã trả model**, ngay khi gọi accessor trên model hoặc model con.

~~~text
parse(badBytes) có thể:
  A. phát hiện lỗi ngay -> IllegalArgumentException
  B. tạo được ClassModel
        |
        +-- thisClass(): đọc được
        |
        +-- methods()/code()/attributes(): gặp phần sai
                                          |
                                          +-- IllegalArgumentException
~~~

Đây là các khả năng được mô tả bởi hợp đồng, không phải khẳng định mọi class file hỏng đều gây lỗi muộn.

**Bắt lỗi quanh toàn bộ quá trình phân tích cần thiết**, thay vì chỉ quanh lời gọi `parse`:

~~~java
try {
    ClassModel model = ClassFile.of().parse(classBytes);
    for (MethodModel method : model.methods()) {
        String name = method.methodName().stringValue();
        // Lưu name vào kết quả phân tích.
    }
} catch (IllegalArgumentException malformed) {
    // Đánh dấu file class không hợp lệ hoặc không hỗ trợ.
}
~~~

Mảnh mã này được đặt trong một method có biến `classBytes`; không phải chương trình độc lập. Nếu đọc file qua `Path`, còn phải xử lý `IOException`. Tránh catch `Throwable` rồi tạo báo cáo “không có method” vì sẽ che lỗi thật.

`ClassFile.verify(bytes)` cung cấp phép kiểm tra class file và trả các lỗi mà verifier tìm thấy. Dùng khi cần xác minh thêm đầu vào/đầu ra, nhất là khi biến đổi bytecode. Nó **có chi phí** và **không thay thế** việc bắt lỗi ở accessor, cũng không chứng minh business logic đúng:

~~~java
var errors = ClassFile.of().verify(classBytes);
if (!errors.isEmpty()) {
    // Xử lý các lỗi được công cụ kiểm tra phát hiện.
}
~~~

Các API liên quan: [ClassFile.parse, verify và transformClass — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html).

## 6. Đa luồng: immutable API không bảo đảm thread-safe

Với đối tượng Java nói chung, hai đặc tính này khác nhau:

- **Immutable public state:** code của caller không có cơ chế sửa trạng thái logic.
- **Thread-safe implementation:** code có thể truy cập đồng thời theo hợp đồng mà không cần external synchronization.

Model Class-File API có đặc tính thứ nhất, nhưng tài liệu cảnh báo **có thể không có đặc tính thứ hai** vì nó lazily inflate. Một phương thức trông như getter có thể tạo/cache model con. Không nên khẳng định một implementation cụ thể sẽ luôn có data race; chỉ cần **API không cam kết an toàn** là đủ để tránh thiết kế phụ thuộc vào điều chưa được bảo đảm.

### 6.1. Các cách chia sẻ và mức an toàn

| Cách làm | Đánh giá |
| --- | --- |
| Mỗi worker nhận bản sao class bytes và tự gọi `parse` | **Khuyến nghị**: model và những accessor lazy thuộc riêng worker |
| Một worker parse rồi trích ra record chỉ chứa `String`, `int` và `List.copyOf(String)` | **Khuyến nghị**: chia sẻ snapshot sau khi publish đúng cách |
| Nhiều worker đồng thời gọi `methods()`, `code()` trên **cùng `ClassModel`** không đồng bộ | **Không có bảo đảm thread-safe** |
| Gọi `model.methods()` một lần rồi coi toàn bộ model đã “warm” | Không đủ: code, attribute, constant pool vẫn có thể lazy |
| Khóa riêng đoạn `parse`, sau đó cho đọc tự do | Không đủ vì parsing có thể tiếp tục khi gọi accessor |
| Dùng chung một `ClassBuilder` hoặc mutable transform state | Không có cơ sở bảo đảm an toàn; tạo builder/transform state riêng cho tác vụ |
| Dùng `ConcurrentHashMap<String, ClassModel>` | Map thread-safe **không làm model bên trong thread-safe** |
| Buộc phải dùng chung một model và mọi model con | Cần đồng bộ **mọi đường truy cập** bằng hợp đồng rõ ràng; thường phức tạp hơn việc xuất immutable DTO |

**Chia sẻ một `MethodModel` vẫn có thể là chia sẻ cùng cây lazy.** Đừng giả định lấy model con ra khỏi `ClassModel` là đã copy toàn bộ nội dung.

### 6.2. Quyền sở hữu bytes

`byte[]` không bất biến. Nếu một thread sửa mảng trong khi parser ở thread khác đang đọc, kết quả không thể xem là snapshot ổn định. Cách đơn giản:

~~~java
byte[] ownedCopy = sourceBytes.clone();
ClassModel localModel = ClassFile.of().parse(ownedCopy);
~~~

Mảnh code này giả định `sourceBytes` đã có và **không có thread nào ghi nó trong lúc copy**. Nếu dữ liệu đến từ file/queue có ownership rõ, worker có thể đọc/copy đúng một lần. Với file lớn, việc nhân bản bytes có chi phí; hãy đo trước khi tối ưu, không để nhiều worker giữ các mảng rất lớn vô hạn.

### 6.3. Publish snapshot dữ liệu

Một kết quả muốn đọc chung an toàn có thể là:

~~~java
record Summary(String name, int major, List<String> methods) {}
~~~

`record` có field bất biến sau khi tạo, nhưng **record có bất biến sâu hay không phụ thuộc các thành phần**. Ở ví dụ đầy đủ bên dưới, danh sách được xây bằng `List.copyOf` và chỉ chứa `String`, nên an toàn để publish theo kênh đồng bộ chuẩn. Nếu dùng `ArrayList` gốc còn bị worker sửa, record không tự sửa được field tham chiếu nhưng dữ liệu bên trong vẫn biến đổi.

Có thể dùng `Future.get()` để nhận kết quả worker: tác động của tính toán trước khi hoàn thành task được publish theo quy tắc bộ nhớ của Future. Đừng thay bằng việc hai thread ghi/đọc cùng static field thông thường mà không có cơ chế đồng bộ.

## 7. Ví dụ chạy độc lập JDK 24+: hai worker phân tích cùng file

**Tại sao JDK 24?** `java.lang.classfile` chuẩn có từ JDK 24, nên ví dụ này chủ ý **không dùng `javac --release 17`**. Với JDK 17–21, package chuẩn này không có; không thể hứa code Java 24 chạy được trên các JDK đó. JDK 22–23 có API preview với các điều kiện và phiên bản khác.

Ví dụ có hai tệp đặt trong cùng thư mục. Ta biên dịch `ExampleService` ra bytecode, rồi hai task phân tích nội dung tương đương nhưng mỗi task có bytes/model riêng.

### 7.1. `ExampleService.java`

~~~java
public final class ExampleService {
    public String status() {
        return "ready";
    }

    public int total(int base) {
        return base + 5;
    }
}
~~~

Ngoài hai method `status` và `total`, compiler tạo constructor mặc định `<init>`.

### 7.2. `ModelConcurrencyDemo.java`

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class ModelConcurrencyDemo {
    record Summary(String internalName, int majorVersion,
                   List<String> methodNames) {}

    private static Summary inspect(byte[] ownedBytes) {
        // Model chỉ được truy cập bên trong một task.
        ClassModel model = ClassFile.of().parse(ownedBytes);

        List<String> names = model.methods().stream()
                .map(method -> method.methodName().stringValue())
                .sorted()
                .toList();

        return new Summary(
                model.thisClass().asInternalName(),
                model.majorVersion(),
                List.copyOf(names));
    }

    public static void main(String[] args) throws Exception {
        byte[] source = Files.readAllBytes(
                Path.of("ExampleService.class"));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            // Mỗi worker nhận bản sao bytes và tự tạo model.
            Future<Summary> first = pool.submit(
                    () -> inspect(source.clone()));
            Future<Summary> second = pool.submit(
                    () -> inspect(source.clone()));

            Summary left = first.get();
            Summary right = second.get();

            System.out.println("name=" + left.internalName());
            System.out.println("major=" + left.majorVersion());
            System.out.println("methods="
                    + String.join(",", left.methodNames()));
            System.out.println("equalSnapshots="
                    + left.equals(right));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Vì model được tạo **bên trong `inspect`** và không trả ra ngoài, không có thread nào khác truy cập vào cùng một cây lazy. Thread chính chỉ nhận record `Summary` chứa `String`, `int` và danh sách chuỗi bất biến. Phép `equals` so sánh **giá trị** hai record, không so sánh identity hai model.

`source.clone()` được thực hiện tại lúc tạo từng task, và `source` không bị sửa. Khi số class lớn, phải giới hạn số worker và lượng dữ liệu trong hàng đợi. `shutdown()` giúp dừng việc nhận task mới; trong code production có thể cần `awaitTermination`/timeout/hủy task theo chính sách.

### 7.3. Biên dịch và kết quả

Dùng **JDK 24 trở lên**, đặt thư mục làm việc tại nơi có hai file:

~~~bash
javac --release 24 ExampleService.java ModelConcurrencyDemo.java
java ModelConcurrencyDemo
~~~

**Stdout dự kiến** khi `ExampleService.class` được biên dịch đúng với `--release 24`:

~~~text
name=ExampleService
major=68
methods=<init>,status,total
equalSnapshots=true
~~~

Class-file major version của Java 24 là **68**. `sorted()` đặt `<init>`, `status` và `total` theo thứ tự ổn định, nên kết quả không phụ thuộc thứ tự worker hoàn thành. Sự bằng nhau chứng minh hai lượt phân tích tạo cùng *snapshot logic*, **không chứng minh cùng một `ClassModel` có thể dùng chung đồng thời**.

## 8. Nếu buộc phải dùng một model chung thì sao?

Cách mặc định vẫn là **model-per-task** hoặc xuất DTO. Khi có yêu cầu đo đạc cụ thể và bắt buộc chỉ giữ một model, phải kiểm soát **mọi truy cập vào cây**: `ClassModel`, các `MethodModel`/`CodeModel` và constant pool/attribute có quan hệ tới nó. Đồng bộ riêng lần `parse` không giúp gì nếu lần accessor tiếp theo mới thực sự inflate.

Việc “prewarm” bằng `model.methods()` rồi publish vẫn không chứng minh an toàn vì một method có thể còn code hoặc attributes chưa đọc. Cũng không có lý do coi builder/transform callback mang mutable state là an toàn chỉ vì input model bất biến.

Nếu lưu cache, **cache snapshot kết quả** là thiết kế dễ quản lý hơn cache model. Key cache có thể cần (tên class, hash/version bytes, nguồn/loader/module), bởi nhiều class loader hoặc bản build có thể cung cấp bytes khác nhau cho **cùng tên class**. Một cache `ConcurrentHashMap<String, ClassModel>` chỉ đồng bộ các thao tác trên map, không tự bổ sung bảo đảm cho nội dung model.

### Cân bằng hiệu năng

Parse mỗi task có thể tạo thêm model và mảng bytes, trong khi parse một lần xuất immutable DTO thường kinh tế hơn nếu nhiều thread cần **cùng dữ liệu**. Hãy đo với workload đại diện:

- Số class file và kích thước trung bình.
- Tỷ lệ truy cập chỉ metadata, cần attributes hay đi sâu bytecode.
- Memory allocation/GC, throughput, latency, số task chạy đồng thời.
- Tỷ lệ class file không hợp lệ và khả năng làm pipeline thất bại.

Một cách giảm công việc là **chỉ duyệt đến cấp cần thiết**: nếu chỉ cần số lượng method, đừng đi sâu `CodeModel`; nếu chỉ vài class cần kiểm tra instruction, lọc bằng metadata trước. Đó là lợi thế thật của lazy parsing.

## 9. Áp dụng vào Java agent và `ClassFileTransformer`

Trong agent, JVM có thể gọi `transform` trên nhiều luồng khi nhiều class đang được load. Mỗi callback nhận `classfileBuffer` cho một lần định nghĩa/biến đổi. Nếu dùng Class-File API, tạo model trong **phạm vi callback** và tránh giữ model trong biến static để thread khác cùng duyệt.

~~~java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    // Lọc phạm vi trước để tránh instrument agent/JDK/logger.
    if (className == null || !className.startsWith("example/app/")) {
        return null;
    }

    ClassModel model = ClassFile.of().parse(classfileBuffer);
    // Đọc các phần cần thiết ngay trong callback hiện tại.
    // Không xuất model sang thread khác để truy cập vô khóa.
    return null; // Transformer này không thay đổi class bytes.
}
~~~

Đây là **mảnh code trong lớp implements `ClassFileTransformer`**, cần các import `ClassFile`/`ClassModel` và agent đăng ký transformer; không phải chương trình độc lập.

Những lưu ý trong thực tế:

1. **Không mutate `classfileBuffer`** JVM cung cấp. Muốn thay class, dùng builder/transform tạo `byte[]` mới.
2. **Không giữ `ClassModel` qua nhiều callback để đọc đồng thời**; callback khác có thể chạy trên thread khác.
3. **Không phân tích mọi class khi không cần**; lọc tên/loader/module phù hợp thật sớm, tránh recursion do chính agent và thư viện logging.
4. **Nếu thực sự cần đổi class ngay trong lần load, phải trả bytes đã biến đổi trong callback**. Đẩy công việc sang background rồi trả `null` không làm lớp hiện tại được sửa.
5. **Cẩn thận lỗi muộn:** `parse` có thể trả model rồi accessor phát hiện bytes sai. Xử lý theo hợp đồng callback và chính sách agent.
6. **Tách khả năng phân tích và quyền áp dụng**: Class-File API đọc/tạo bytes; `Instrumentation` và JVM quyết định class đang load/có thể retransform/redefine hay không.

Nếu chỉ muốn phân tích ngoại tuyến, pipeline bên ngoài JVM/agent sẽ tránh được nhiều giới hạn classloading và tác động tới ứng dụng đang chạy.

## 10. Những sai lầm thường gặp

| Nhận định sai | Vì sao sai? | Hướng đúng |
| --- | --- | --- |
| “Immutable = thread-safe.” | Lazy inflation có thể có trạng thái nội bộ phát sinh khi đọc | Model riêng theo worker hoặc xuất DTO bất biến |
| “`parse` chạy xong nghĩa là đã parse mọi phần.” | Truy cập `code`/attribute có thể phân tích muộn | Xem mức dữ liệu cần thiết và bắt lỗi ở accessor |
| “Bắt exception quanh mỗi `parse` là đủ.” | Lỗi `IllegalArgumentException` có thể xuất hiện sau đó | Bắt quanh cả lần truy vấn |
| “Chia sẻ `List<MethodModel>` đã copy là an toàn.” | Thành phần vẫn là lazy model | Trích tên/descriptor thành `String` và copy |
| “`byte[]` không ai sửa được.” | Mảng Java mutable | Giữ quyền sở hữu hoặc clone |
| “`methods()` một lần đã warm toàn bộ code.” | Method body có thể chưa được inflate | Không coi warm-up là chứng nhận thread safety |
| “Synchronized `parse` xong có thể đọc model chung.” | Hoạt động lazy diễn ra sau parse | Đồng bộ mọi đường đọc hoặc tránh chia sẻ |
| “`ConcurrentHashMap` bảo vệ `ClassModel`.” | Chỉ các thao tác map có bảo đảm đồng bộ | Cache DTO thực sự bất biến |
| “Builder cũng bất biến vì model bất biến.” | Builder phục vụ quá trình tạo output, có trạng thái | Builder riêng mỗi tác vụ/output |
| “Java 17 có `java.lang.classfile` chuẩn.” | API chuẩn có từ JDK 24 | Chạy bằng JDK 24+ |
| “Parse `.class` tương đương class loading.” | `ClassModel` là biểu diễn bytes, không phải `Class<?>` | Giữ hai mô hình khái niệm riêng |
| “Có thể sửa bytes sau khi callback đã trả `null`.” | Callback đó đã thông báo không biến đổi | Biến đổi và trả bytes ngay theo hợp đồng |

## 11. Quy trình thiết kế pipeline an toàn

~~~text
Input .class -> nhận diện nguồn/version/hash
            -> giới hạn số worker
            -> copy/đọc bytes thuộc worker
            -> ClassFile.of().parse riêng
            -> đọc đúng metadata/code cần thiết
            -> bắt lỗi parse lẫn accessor
            -> immutable Summary/DTO
            -> publish qua Future/queue có đồng bộ
            -> cache kết quả và xuất báo cáo
~~~

Checklist kỹ thuật:

- [ ] Đúng JDK hỗ trợ Class-File API đang dùng.
- [ ] Mảng bytes không bị sửa trong khi phân tích.
- [ ] Không dùng chung `ClassModel`/model con nếu không có đồng bộ đầy đủ.
- [ ] Kết quả qua ranh giới thread chứa dữ liệu đã trích và bất biến sâu.
- [ ] Chỉ truy cập phần class file thực sự cần.
- [ ] Xử lý `IllegalArgumentException` từ `parse` **và** accessor.
- [ ] Task pool/cache có giới hạn, đúng ownership và cache key.
- [ ] Có kiểm thử input lỗi, class lớn, class loader/version khác nhau và cạnh tranh đồng thời.

### Tự kiểm tra

1. Vì sao `ClassModel` là immutable nhưng không được mặc định thread-safe?
2. Lệnh `model.methods().size()` có nhất thiết giải mã toàn bộ bytecode không?
3. Vì sao lỗi về class file có thể ném ở `method.code()` sau một lần `parse` thành công?
4. Trong ví dụ hai worker, tại sao `source.clone()` và `Summary` được dùng cùng nhau?
5. Vì sao không nên dùng `List.copyOf(model.methods())` như snapshot chia sẻ?
6. Nếu cache theo tên lớp, trường hợp class loader hoặc bản build khác nhau gây sai như thế nào?
7. Tại sao không nên cho thread nền truy cập `ClassModel` nhận được trong callback transformer?
8. Khi cần sửa bytecode, tại sao builder/transform trả bytes mới thay vì sửa model?
9. Vì sao code mẫu yêu cầu JDK 24 dù rất nhiều ví dụ Java thông thường chạy trên Java 17?

**Ghi nhớ:** Class-File API có **biểu diễn logic bất biến** và **phân tích theo nhu cầu**. Hai thuộc tính này giúp việc đọc và biến đổi bytecode hiệu quả, nhưng do lazy inflation, tài liệu **không cam kết model thread-safe**. Hãy giữ model trong phạm vi một task hoặc đồng bộ mọi đường truy cập; cách dễ kiểm thử nhất là trả về **snapshot giá trị bất biến** cho các thread khác.

### Tài liệu chính thức

- [Java 24 — java.lang.classfile: model bất biến, lazy parsing, thread-safety](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html)
- [Java 24 — ClassFile: parse, transformClass, verify](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [Java 24 — ClassModel](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassModel.html)
- [Java 24 — MethodModel](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodModel.html)
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484)
