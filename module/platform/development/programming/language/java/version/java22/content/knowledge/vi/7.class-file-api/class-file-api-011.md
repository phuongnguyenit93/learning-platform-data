# Phiên bản class file, thuộc tính mới và giới hạn tương thích giữa các JDK

Mỗi file `.class` mang theo phiên bản định dạng mà JVM phải hiểu. Phiên bản này được biểu diễn bằng hai số **major.minor**. Khi một JDK mới bổ sung cấu trúc constant pool, bytecode hoặc thuộc tính class file, khả năng đọc file của các JDK cũ có thể bị giới hạn.

Vì vậy, khi phát hành thư viện hoặc ứng dụng Java, cần xác định JDK thấp nhất mà chương trình phải chạy, chọn đúng mức bytecode, kiểm tra các thuộc tính và cấu trúc mới được sử dụng, đồng thời bảo đảm mọi dependency có cùng mức tương thích. Bài học dùng Java 27 làm mốc hiện hành tại ngày 25-11-2026: JDK 27 đã GA từ tháng 9-2026, major version là 71; JDK 25 là bản LTS mới nhất. [Nguồn phát hành Java 27](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/).

## 1. Cấu trúc và ý nghĩa của phiên bản class file

Class file là định dạng nhị phân mà JVM nạp, liên kết và xác minh. Phần đầu file có magic number `0xCAFEBABE`, sau đó là hai trường phiên bản:

```text
ClassFile {
    u4 magic;          // 0xCAFEBABE
    u2 minor_version;
    u2 major_version;
    u2 constant_pool_count;
    cp_info constant_pool[...];
    u2 access_flags;
    u2 this_class;
    u2 super_class;
    ...
    field_info fields[...];
    method_info methods[...];
    attribute_info attributes[...];
}
```

`major_version` xác định thế hệ định dạng class file. `minor_version` bổ sung thông tin trong cùng major version; từ Java 12, nó còn được dùng để đánh dấu class file phụ thuộc vào preview feature của một release cụ thể.

Phiên bản class file không phải phiên bản mã nguồn. Ví dụ, mã Java có thể được viết bằng cú pháp Java 17, biên dịch bởi JDK 27 và tạo ra class file major 61 nếu dùng `--release 17`.

## 2. Bảng major version từ Java 8 đến Java 27

Các major version thường gặp:

| Java SE | Major version | Ví dụ định dạng stable |
|---:|---:|---:|
| 8 | 52 | `52.0` |
| 9 | 53 | `53.0` |
| 10 | 54 | `54.0` |
| 11 | 55 | `55.0` |
| 12 | 56 | `56.0` |
| 13 | 57 | `57.0` |
| 14 | 58 | `58.0` |
| 15 | 59 | `59.0` |
| 16 | 60 | `60.0` |
| 17 | 61 | `61.0` |
| 18 | 62 | `62.0` |
| 19 | 63 | `63.0` |
| 20 | 64 | `64.0` |
| 21 | 65 | `65.0` |
| 22 | 66 | `66.0` |
| 23 | 67 | `67.0` |
| 24 | 68 | `68.0` |
| 25 | 69 | `69.0` |
| 26 | 70 | `70.0` |
| 27 | 71 | `71.0` |

Theo Java Virtual Machine Specification phiên bản 27, JVM tương thích Java SE 27 hỗ trợ major version từ 45 đến 71. Các major version cũ hơn trong dải này vẫn được hỗ trợ. Một JVM cũ không thể nạp class file có major version cao hơn mức nó hỗ trợ; lỗi thường gặp là `UnsupportedClassVersionError`.

Ví dụ:

- JDK 17 hỗ trợ class file tới major 61.
- JDK 22 hỗ trợ tới major 66.
- JDK 25 hỗ trợ tới major 69.
- JDK 27 hỗ trợ tới major 71.

Vì thế, class file `71.0` chạy được trên JDK 27 nhưng không chạy trực tiếp trên JDK 25. Ngược lại, class file `61.0` có thể được JVM mới hơn nạp nếu nó không phụ thuộc vào API hoặc hành vi chỉ có ở JDK mới.

## 3. Minor version và dấu hiệu preview

Với class file từ Java 12 trở đi (major 56 trở lên), `minor_version` hợp lệ chỉ có hai giá trị:

| Minor version | Ý nghĩa |
|---:|---|
| `0` | Class file dùng định dạng stable của major version đó. |
| `65535` | Class file phụ thuộc vào preview feature của đúng release Java tương ứng với major version. |

Trước Java 12, minor version có lịch sử khác; đối với major version từ 45 đến 55, đặc tả cho phép các giá trị minor khác nhau. Khi phát triển và kiểm tra class file hiện đại, cần tập trung vào hai giá trị `0` và `65535`.

### Ví dụ preview trong Java 27

Java 27 hiện có preview language feature (Primitive Types in Patterns); JVMS 27 không định nghĩa preview VM feature. Khi biên dịch mã sử dụng cú pháp preview, compiler vẫn tạo class file `71.65535`. Phải bật preview ở cả lúc biên dịch và chạy:

```bash
javac --enable-preview --release 27 -d out src/demo/Main.java
java --enable-preview -cp out demo.Main
```

Class file preview bị ràng buộc vào release đã tạo ra nó. Ví dụ:

- `66.65535` là class file phụ thuộc preview của Java 22.
- `71.65535` là class file phụ thuộc preview của Java 27.

Class file `66.65535` chỉ có thể được nạp bởi JVM Java 22 khi preview được bật. JDK 27 không thể nạp nó, kể cả khi chạy với `--enable-preview`. Tương tự, class file `71.65535` chỉ chạy trên JDK 27 có bật preview. Đây là giới hạn có chủ đích vì preview feature có thể thay đổi hoặc biến mất giữa các release.

Lưu ý: dấu minor `65535` không có nghĩa toàn bộ Class-File API đang ở trạng thái preview. Class-File API được chuẩn hóa trong Java 24 qua JEP 484 và vẫn là API stable trong JDK 27. Minor version `65535` đánh dấu **class file cụ thể** có sử dụng preview feature của release tương ứng.

## 4. Những thuộc tính class file quan trọng được bổ sung theo thời gian

Attribute là metadata được gắn vào class, field, method, phần `Code` hoặc record component. Mỗi attribute có tên, độ dài và vùng dữ liệu riêng. Không phải mọi attribute đều có cùng vai trò: một số cần cho JVM diễn giải bytecode đúng, một số phục vụ thư viện Java, reflection hoặc công cụ phát triển.

Các attribute hiện hành đáng chú ý:

| Java SE đầu tiên | Class file | Attribute | Vai trò |
|---:|---:|---|---|
| 6 | `50.0` | `StackMapTable` | Cung cấp stack map frame phục vụ xác minh bytecode. |
| 7 | `51.0` | `BootstrapMethods` | Mô tả bootstrap method dùng cho `invokedynamic` và các constant động. |
| 8 | `52.0` | `MethodParameters` | Lưu metadata về tên và cờ của tham số phương thức. |
| 8 | `52.0` | `RuntimeVisibleTypeAnnotations`, `RuntimeInvisibleTypeAnnotations` | Lưu type annotation tại các vị trí kiểu được hỗ trợ. |
| 9 | `53.0` | `Module`, `ModulePackages`, `ModuleMainClass` | Mô tả module, package được module chứa và lớp main của module. |
| 11 | `55.0` | `NestHost`, `NestMembers` | Mô tả quan hệ nest để các lớp lồng nhau truy cập private member theo quy tắc nestmate. |
| 16 | `60.0` | `Record` | Đánh dấu record class và mô tả record component. |
| 17 | `61.0` | `PermittedSubclasses` | Lưu danh sách lớp con được phép của sealed class/interface. |

JVM Specification Java 27 hiện vẫn liệt kê 30 predefined attributes; các attribute mới nhất trong danh sách này là `Record` từ Java 16 và `PermittedSubclasses` từ Java 17. Không có predefined attribute mới được thêm vào đặc tả class file trong các release Java 18 đến Java 27.

### Phân biệt attribute quan trọng với metadata

JVMS chia predefined attributes thành các nhóm theo vai trò:

- **Cần cho JVM diễn giải đúng class file**: ví dụ `Code`, `StackMapTable`, `BootstrapMethods`, `NestHost`, `NestMembers`, `PermittedSubclasses` và `ConstantValue`.
- **Quan trọng với class library hoặc công cụ**: ví dụ `Record`, `Signature`, `InnerClasses`, `Exceptions`, `SourceFile` và các bảng debug.
- **Metadata có thể được thư viện hoặc công cụ sử dụng**: ví dụ annotation, `MethodParameters` và module metadata.

Ví dụ, `PermittedSubclasses` là attribute JVM phải hiểu để thực thi quy tắc sealed hierarchy. `Record` lại quan trọng đối với class library Java để nhận diện record và cung cấp reflection về record component. Các annotation runtime-visible được reflection đọc; annotation runtime-invisible thường phục vụ công cụ xử lý ở thời điểm biên dịch hoặc build.

Không nên coi mọi attribute là thông tin tùy chọn có thể xóa mà không ảnh hưởng. Xóa hoặc làm sai attribute có thể phá vỡ xác minh bytecode, ngữ nghĩa sealed type, reflection, module resolution hoặc công cụ build.

## 5. Attribute tùy biến và cách JVM xử lý attribute chưa biết

JVMS cho phép compiler hoặc công cụ phát sinh attribute riêng. Ví dụ, một công cụ phân tích bytecode có thể ghi metadata phục vụ debug hoặc tối ưu hóa riêng. Tuy nhiên, attribute không thuộc đặc tả JVM **không được thay đổi ngữ nghĩa thực thi của class file**.

JVM phải âm thầm bỏ qua attribute mà nó không nhận diện. Điều này cho phép một class file chứa metadata riêng vẫn có thể được JVM khác nạp nếu phần cấu trúc chuẩn của nó tương thích. Công cụ cần metadata riêng vẫn phải hiểu attribute đó; nếu thiếu, chức năng của công cụ có thể không hoạt động đúng.

Quy tắc bỏ qua attribute không có nghĩa class file dùng một định dạng major mới sẽ chạy trên JVM cũ. JVM vẫn kiểm tra major/minor version, constant pool, opcode, các attribute chuẩn quan trọng và những ràng buộc cấu trúc khác. Một class file major 71 vẫn bị JDK 25 từ chối trước khi khả năng bỏ qua custom attribute có ý nghĩa.

Khi tạo custom attribute:

- Chọn tên có namespace theo quy tắc đặt tên Java để tránh trùng tên với attribute của JVM hoặc công cụ khác.
- Không dùng custom attribute để thay đổi ngữ nghĩa bytecode mà JVM phải hiểu.
- Ghi rõ công cụ nào cần đọc attribute và điều gì xảy ra nếu attribute bị bỏ qua.
- Bảo đảm các công cụ transform class file giữ lại, cập nhật hoặc loại bỏ metadata theo cách có chủ đích.

## 6. Một số thay đổi trong constant pool cũng ảnh hưởng tương thích

Không phải mọi thay đổi của định dạng class file đều là attribute. Constant pool cũng được mở rộng theo từng thế hệ:

| Java SE đầu tiên | Major version | Constant pool entry mới | Mục đích |
|---:|---:|---|---|
| 7 | `51.0` | `CONSTANT_MethodHandle`, `CONSTANT_MethodType`, `CONSTANT_InvokeDynamic` | Hỗ trợ method handle, method type và `invokedynamic`. |
| 9 | `53.0` | `CONSTANT_Module`, `CONSTANT_Package` | Biểu diễn module và package trong module descriptor. |
| 11 | `55.0` | `CONSTANT_Dynamic` | Biểu diễn hằng số được tính toán động qua bootstrap method. |

Một class file phải dùng constant pool tag được định nghĩa ở phiên bản định dạng đó hoặc cũ hơn. Do vậy, chỉ sửa hai byte major version trong header không thể làm class file hiện đại trở thành class file cũ hợp lệ. Nếu bên trong vẫn còn constant pool tag, opcode, attribute hoặc cấu trúc chỉ có ở phiên bản mới, JVM cũ vẫn không thể diễn giải đúng.

## 7. Cách đọc phiên bản bằng công cụ hiện hành

### Dùng `javap`

Lệnh sau in thông tin chi tiết của class file:

```bash
javap -verbose -classpath out demo.Main
```

Trong kết quả, tìm các dòng:

```text
minor version: 0
major version: 71
```

Nếu thấy `minor version: 65535`, file phụ thuộc preview feature của release tương ứng với major version. `javap` cũng hiển thị constant pool, flags, descriptors và attributes, rất hữu ích khi điều tra lỗi tương thích.

### Dùng Class-File API stable

Class-File API nằm trong package `java.lang.classfile`, thuộc module `java.base`. API này từng preview trong Java 22 (JEP 457), preview lần hai trong Java 23 (JEP 466), rồi final từ Java 24 (JEP 484). JDK 27 dùng API stable, không cần `--enable-preview`.

Ví dụ đọc major/minor version từ một file:

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Path;

public class InspectClassVersion {
    public static void main(String[] args) throws Exception {
        Path classPath = Path.of(args[0]);
        ClassModel model = ClassFile.of().parse(classPath);

        System.out.printf(
            "Class: %s, version: %d.%d%n",
            model.thisClass().asInternalName(),
            model.majorVersion(),
            model.minorVersion()
        );

        System.out.println(
            "Runtime supports major up to: " + ClassFile.latestMajorVersion()
        );
    }
}
```

Chạy bằng JDK 27:

```bash
javac InspectClassVersion.java
java InspectClassVersion out/demo/Main.class
```

`ClassModel.majorVersion()` và `minorVersion()` trả về hai giá trị trong header; `ClassFile.latestMajorVersion()` cho biết major version mới nhất mà runtime hiện tại hỗ trợ. Class-File API cũng cung cấp `ClassFileVersion` để mô hình hóa cặp major/minor và `ClassFileFormatVersion` trong `java.lang.reflect` để làm việc với major version.

## 8. Đặt phiên bản mục tiêu khi sinh class file

Nếu dùng Class-File API để sinh class file, có thể đặt phiên bản rõ ràng bằng `ClassBuilder.withVersion(major, minor)`. Ví dụ dưới đây tạo một class tối thiểu có định dạng Java 17:

```java
import java.lang.classfile.ClassFile;
import java.lang.constant.ClassDesc;
import java.lang.constant.ConstantDescs;

public class GenerateJava17Class {
    public static void main(String[] args) {
        byte[] bytes = ClassFile.of().build(
            ClassDesc.of("demo.Generated"),
            classBuilder -> classBuilder
                .withVersion(ClassFile.JAVA_17_VERSION, 0)
                .withFlags(ClassFile.ACC_PUBLIC)
                .withSuperclass(ConstantDescs.CD_Object)
        );

        System.out.println("Generated bytes: " + bytes.length);
    }
}
```

`ClassFile.JAVA_17_VERSION` là major version 61. Tham số minor `0` chọn định dạng stable. Khi chọn phiên bản thấp hơn, người sinh bytecode phải bảo đảm toàn bộ nội dung class file cũng tương thích với phiên bản đó: không thêm attribute chuẩn mới hơn, constant pool tag mới hơn, opcode hoặc cấu trúc mà JVM đích chưa hỗ trợ. Chỉ đặt header về major cũ không đủ để bảo đảm tương thích.

## 9. Chọn target và kiểm soát tương thích giữa các JDK

Với source code thông thường, nên dùng `javac --release` thay vì chỉ kết hợp `-source` và `-target`:

```bash
# Biên dịch bằng JDK 27 nhưng tạo class file tương thích Java 17.
javac --release 17 -d out src/demo/Main.java
```

`--release 17` kết hợp ba ràng buộc:

1. Dùng quy tắc ngôn ngữ Java 17 khi biên dịch.
2. Chỉ cho phép dùng API Java/JDK có trong release 17.
3. Tạo class file có major version 61.

Nếu chỉ dùng `-target 17`, compiler có thể vẫn cho phép tham chiếu API chỉ có ở JDK 27, khiến chương trình biên dịch thành công nhưng lỗi khi chạy trên JDK 17. `--release` giúp tránh lỗi này ở phần code được biên dịch.

`--release` không tự hạ phiên bản bytecode của các thư viện bên thứ ba. Nếu dependency được biên dịch cho major 71, ứng dụng target 17 vẫn không chạy trên JDK 17. Cần kiểm tra tất cả JAR, plugin, annotation processor, agent và code được sinh trong build.

Các nguyên tắc thực tế:

- Xác định JDK thấp nhất mà môi trường triển khai yêu cầu, rồi đặt `--release` theo phiên bản đó.
- Dùng cùng target trong CI, local build và pipeline phát hành.
- Kiểm tra dependency bytecode, đặc biệt khi thư viện được cập nhật lên bản build bằng JDK mới.
- Tránh sửa trực tiếp major/minor trong header bằng hex editor hoặc script đơn giản.
- Nếu dùng preview feature, giữ toàn bộ quá trình biên dịch và chạy trên đúng JDK release; không dùng preview cho artifact cần phân phối rộng hoặc chạy qua nhiều JDK.
- Với class file sinh bởi bytecode generator, dùng Class-File API stable và xác minh file sau khi build.

## 10. Các kiểu tương thích cần phân biệt

Một class file có thể vượt qua kiểm tra major version nhưng chương trình vẫn không chạy được. Nên phân biệt:

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| Định dạng bytecode | JVM có hiểu major/minor, constant pool, opcode và attributes không? | `UnsupportedClassVersionError`, `ClassFormatError`, `VerifyError`. |
| API/runtime | Các class, method, field mà chương trình gọi có tồn tại trên JDK đích không? | `NoClassDefFoundError`, `NoSuchMethodError`, `NoSuchFieldError`. |
| Module và dependency | Module, package, service và thư viện phụ thuộc có sẵn và được cấu hình đúng không? | `FindException`, `LayerInstantiationException`, lỗi class loading. |
| Hành vi | API có cùng hành vi hoặc chính sách runtime giữa các JDK không? | Thay đổi hành vi, cảnh báo mới, lỗi bảo mật hoặc cấu hình. |

Tương thích định dạng class file chỉ là một lớp trong bài toán tương thích tổng thể. JDK mới thường hỗ trợ class file cũ, nhưng không thể tự bổ sung API hoặc dependency mà chương trình đang cần.

## 11. Checklist trước khi phát hành thư viện hoặc ứng dụng

- Xác định major/minor của class file được sinh ra.
- Đặt `--release` theo JDK thấp nhất được hỗ trợ.
- Kiểm tra mọi dependency có major version không vượt quá runtime mục tiêu.
- Kiểm tra constant pool tags và predefined attributes mới được sử dụng.
- Không phát hành class file preview như artifact stable.
- Nếu dùng custom attributes, xác định rõ công cụ nào cần đọc chúng.
- Dùng `javap -verbose` hoặc Class-File API để kiểm tra artifact.
- Chạy integration test trên JDK thấp nhất được hỗ trợ và trên JDK hiện hành.

## 12. Kết luận

Phiên bản class file là cặp `major.minor`, trong đó major xác định thế hệ định dạng và minor từ Java 12 có thể đánh dấu preview bằng giá trị `65535`. JDK 27 hiện hỗ trợ major 45 đến 71; class file mới hơn runtime sẽ bị từ chối, còn class file preview chỉ được nạp bởi đúng release đã tạo nó khi preview được bật.

Attributes và constant pool được mở rộng theo từng release. Các attribute như `Module`, `NestHost`, `Record` và `PermittedSubclasses` phản ánh các khả năng mới của nền tảng, trong khi custom attributes phải tuân theo quy tắc không làm thay đổi ngữ nghĩa JVM. Để giữ tương thích, hãy chọn target bằng `--release`, kiểm tra cả dependency và dùng Class-File API stable từ Java 24 khi cần phân tích hoặc sinh class file.

## Tài liệu tham khảo

- [Java Virtual Machine Specification – Java SE 27, Chapter 1: Introduction](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-1.html)
- [Java Virtual Machine Specification – Java SE 27, Chapter 4: The Class File Format](https://docs.oracle.com/en/java/javase/27/docs/specs/jvms/jvms-4.html)
- [Java SE 27 `javac` Command – `--release` and `--enable-preview`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [JEP 484 – Class-File API](https://openjdk.org/jeps/484)
- [JEP 466 – Class-File API (Second Preview)](https://openjdk.org/jeps/466)
- [JEP 457 – Class-File API (Preview)](https://openjdk.org/jeps/457)
- [ClassFile – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [ClassModel – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassModel.html)
- [ClassFileVersion – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFileVersion.html)
