# Phiên bản class file và tính hợp lệ của bytecode khi định nghĩa hidden class (Java 15+)

## Mục tiêu

Hiểu **vì sao một mảng byte[] chưa chắc là class file hợp lệ**, cách phiên bản **major.minor** quyết định JVM nào có thể tiếp nhận bytecode, và các điều kiện bổ sung khi dùng **MethodHandles.Lookup.defineHiddenClass(...)** để tạo hidden class. Biết phân biệt lỗi **UnsupportedClassVersionError**, **ClassFormatError**, **VerifyError**, **IllegalArgumentException** và một số lỗi liên kết; biết kiểm tra class file bằng **javap** và thử nghiệm an toàn với bytecode do trình biên dịch tạo ra.

Hidden class được giới thiệu trong Java 15 và vẫn là cơ chế JVM chính thức trong Java 17 trở lên. Nội dung sau chỉ sử dụng quy tắc hiện hành của Java/JVM; ví dụ được biên dịch ở chế độ tương thích **Java 17**.

## 1. defineHiddenClass cần loại dữ liệu gì?

Một hidden class **không được tạo bằng cách truyền bất kỳ byte[] nào**. Phương thức nhận **toàn bộ class file đúng định dạng JVM**:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(classBytes, true);
Class<?> hiddenClass = hiddenLookup.lookupClass();
~~~

Đây là hai dòng **minh họa bên trong phương thức Java**: biến classBytes phải là byte[] chứa một class file hợp lệ; phương thức gọi cần xử lý hoặc khai báo IllegalAccessException và các lỗi có thể phát sinh. Chương trình chạy hoàn chỉnh nằm ở mục 7.

Một class file hợp lệ phải thỏa mãn đồng thời:

1. **Định dạng nhị phân đúng** theo *Java Virtual Machine Specification* (JVMS), gồm magic, bảng hằng, thông tin lớp, phương thức, trường, thuộc tính…
2. **Phiên bản major/minor được JVM hiện tại hỗ trợ**.
3. **Tên lớp trong this_class hợp lệ** và thuộc **cùng package** với lookup class; class file phải biểu diễn lớp hoặc interface thích hợp.
4. **Các ràng buộc cấu trúc, kiểu dữ liệu và bytecode JVM** cho phép lớp được xác minh (verification) và liên kết (linking).
5. **Lookup có quyền thích hợp**; defineHiddenClass yêu cầu **full privilege access** theo hợp đồng API.

Vì thế, **đúng phiên bản chỉ là điều kiện cần, không phải điều kiện đủ**. Một class file mang version 61.0 vẫn bị từ chối nếu bảng hằng bị hỏng, mã lệnh không qua bộ xác minh, package không tương thích hoặc phụ thuộc không liên kết được.

## 2. Header class file và major/minor

Theo JVMS, các trường đầu tiên của một class file được lưu theo thứ tự sau, số nguyên nhiều byte ở dạng **big-endian**:

| Offset tính từ 0 | Số byte | Trường | Ý nghĩa |
| ---: | ---: | --- | --- |
| 0–3 | 4 | **magic** | Phải là **0xCAFEBABE** |
| 4–5 | 2 | **minor_version** | Phần phiên bản phụ |
| 6–7 | 2 | **major_version** | Phần phiên bản chính |
| 8–9 | 2 | **constant_pool_count** | Số đếm mục trong bảng hằng theo quy tắc JVMS |
| Các byte tiếp theo | Thay đổi | **constant_pool**, **access_flags**, **this_class**… | Cấu trúc và nội dung còn lại của class file |

Ví dụ, file **61.0** là **major = 61**, **minor = 0**, tương ứng với định dạng được giới thiệu ở Java 17. Không nên đọc nhầm hai trường: trong file nhị phân **minor nằm trước major**, dù thường viết nhãn version là **major.minor**.

Có thể đọc header bằng Java, nhưng phải bảo đảm byte[] có tối thiểu 8 byte và hiểu nó chỉ là bước kiểm tra ban đầu:

~~~java
int minor = ((bytes[4] & 0xff) << 8) | (bytes[5] & 0xff);
int major = ((bytes[6] & 0xff) << 8) | (bytes[7] & 0xff);
~~~

Đoạn code trên **giả định biến bytes kiểu byte[] chứa ít nhất 8 byte**; nó chưa xác minh toàn bộ class file. **& 0xff** chuyển byte có dấu của Java sang giá trị 0–255 trước khi ghép hai byte thành số nguyên không dấu 16 bit.

## 3. Phiên bản class file nào được hỗ trợ?

Bảng sau thể hiện **major version được giới thiệu** theo các phiên bản Java tiêu biểu:

| Java SE / JDK | Class file major | Class file thông thường |
| --- | ---: | --- |
| Java 8 | 52 | 52.0 |
| Java 11 | 55 | 55.0 |
| **Java 15** | **59** | **59.0** |
| **Java 17** | **61** | **61.0** |
| Java 21 | 65 | 65.0 |
| Java 25 | 69 | 69.0 |

Trong JVM phù hợp chuẩn Java 17, class file có major **lớn hơn 61** không được hỗ trợ. JVM của Java 25 hỗ trợ major tối đa **69**. Quy tắc cụ thể phụ thuộc phiên bản JVM thực sự chạy ứng dụng; JDK dùng để **biên dịch** và JVM dùng để **chạy** có thể là hai phiên bản khác nhau.

Ví dụ: một class file biên dịch với **javac --release 17** mang major **61**, và có thể được JVM Java 17 hoặc JVM mới hơn hỗ trợ theo quy tắc tương thích. Nếu biên dịch bằng JDK mới mà không thiết lập mục tiêu tương thích, compiler có thể tạo file version mới hơn, khiến JVM cũ ném **UnsupportedClassVersionError**.

Đối với **defineHiddenClass**, quy tắc về version **cũng áp dụng**: bytecode dùng để tạo hidden class phải có major/minor được **JVM hiện tại chấp nhận**. Phiên bản bytecode của hidden class **không bắt buộc bằng** phiên bản của lookup class; chúng có thể khác nhau nếu cả hai đều được JVM hỗ trợ.

### Quy tắc minor_version và preview

Với **major từ 56 trở lên** (Java 12+), **minor_version chỉ được là 0 hoặc 65535** theo định dạng JVMS hiện hành:

- **minor 0:** class file không mang dấu hiệu dùng preview feature, vẫn phải thỏa điều kiện major và bytecode hợp lệ.
- **minor 65535:** class file được đánh dấu phụ thuộc **preview features của đúng bản Java tương ứng với major**; muốn nạp phải chạy **đúng bản JVM đó** và bật preview theo cơ chế tương ứng, thông thường **--enable-preview**.
- Một class file preview của bản Java cũ **không được chạy trên JVM mới hơn** chỉ nhờ bật --enable-preview. Ví dụ file **61.65535** gắn với Java 17 không trở thành hợp lệ trên Java 25.
- Với major quá cao, minor không được hỗ trợ hoặc bản preview không khớp, việc định nghĩa hidden class có thể ném **UnsupportedClassVersionError**.

**Đừng sửa byte version thủ công để “nâng cấp” hoặc “hạ cấp” class file.** Header chỉ là khai báo định dạng; các instruction, constant-pool entry và attribute bên trong có thể phụ thuộc vào một phiên bản JVM cụ thể. Muốn tạo file tương thích, hãy **biên dịch với --release** phù hợp hoặc dùng công cụ biến đổi class file tuân thủ đầy đủ JVMS và kiểm thử kết quả.

## 4. Bytecode hợp lệ còn đòi hỏi những gì?

### 4.1. Cấu trúc class file và bảng hằng

JVM phải đọc được cấu trúc ClassFile, các số đếm và độ dài dữ liệu, constant pool và các chỉ số tham chiếu hợp lệ. Ví dụ:

- magic **0xCAFEBABE** đúng; dữ liệu không bị thiếu hoặc hỏng;
- **constant_pool_count**, loại mục và chỉ số tham chiếu vào constant pool nhất quán;
- **this_class** chỉ đến một mục **CONSTANT_Class_info** hợp lệ;
- định dạng trường, phương thức, descriptor, access flags, Code attribute và các attribute khác tuân thủ JVMS;
- file class biểu diễn class hoặc interface; file **module-info** có cờ **ACC_MODULE** không được dùng như một class/interface để định nghĩa hidden class.

Trường hợp dữ liệu không phải một cấu trúc ClassFile hợp lệ thường dẫn đến **ClassFormatError**. Điều này khác với một file có cấu trúc đúng nhưng **phiên bản chưa được JVM hỗ trợ**, có thể dẫn đến UnsupportedClassVersionError.

### 4.2. Quy tắc this_class và package

**defineHiddenClass** nhận class file có this_class biểu diễn một tên nhị phân hợp lệ **thuộc cùng package với lookup class**. Ví dụ, nếu code tạo hidden class đang ở package **demo.hidden**, bytecode được dùng cũng phải có khai báo package tương ứng.

JVM dùng thông tin **this_class** từ bytecode làm cơ sở, sau đó thêm hậu tố định danh đặc biệt khi tạo hidden class. Bạn **không cần tự chèn một “hidden flag” hoặc sửa tên thành tên có dấu /** trong class file đầu vào.

Nếu tên lớp trong bytecode thuộc **package khác** với lookup class, phương thức có thể ném **IllegalArgumentException**. Điều kiện **same package** không được bỏ qua chỉ vì đó là hidden class hoặc do code có thể truy cập được public method của lớp khác.

Không nên dùng thủ thuật thay chuỗi tên trong constant pool bằng phép tìm và thay byte đơn giản: tên, descriptor và các tham chiếu trong class file có cấu trúc chặt chẽ. Nếu cần sinh class file, dùng compiler hoặc API/thư viện class-file phù hợp với phiên bản Java đích.

### 4.3. Bộ xác minh bytecode (verification)

Một class file có header đúng và bảng hằng có vẻ hợp lệ **vẫn có thể bị từ chối khi xác minh** nếu bytecode vi phạm quy tắc JVM, chẳng hạn:

- thao tác trên operand stack với **kiểu dữ liệu không phù hợp**;
- dùng biến cục bộ trước khi được khởi tạo hợp lệ hoặc sai kiểu;
- luồng điều khiển, stack-map frame hoặc vị trí nhảy không nhất quán;
- lệnh bytecode không hợp lệ với loại giá trị mà nó thao tác;
- vi phạm một ràng buộc kiểu của class file tương ứng với version khai báo.

Các tình huống như vậy có thể dẫn đến **VerifyError**. Một số lỗi kiểm tra, liên kết hay giải quyết tham chiếu có thể được phát hiện trong quá trình định nghĩa lớp hoặc muộn hơn khi lớp/thành viên được sử dụng, tùy quy tắc JVM và thời điểm liên kết/khởi tạo. Vì vậy, việc tạo Class object thành công **không thay cho kiểm thử runtime của hành vi được sinh ra**.

### 4.4. Liên kết, quyền truy cập và phụ thuộc

Ngay cả bytecode có thể xác minh cũng cần liên kết đúng: lớp cha, các interface, trường và phương thức được tham chiếu phải phù hợp. Ví dụ, khai báo một interface như superclass có thể gây **IncompatibleClassChangeError**; quan hệ kế thừa tạo vòng có thể gây **ClassCircularityError**; phụ thuộc không tìm được hoặc các sai lệch liên kết khác thuộc họ **LinkageError**.

Phương thức **defineHiddenClass** cũng kiểm tra quyền của **MethodHandles.Lookup**. Lookup cần **full privilege access**; thiếu quyền có thể gây **IllegalAccessException**. Đây là điều kiện riêng của API, **không phải** vấn đề phiên bản class file.

Tham số **initialize** của defineHiddenClass điều khiển thời điểm **khởi tạo lớp**. Giá trị **true** yêu cầu khởi tạo lớp được tạo; giá trị **false** không yêu cầu khởi tạo ngay. Đừng hiểu **false** là bỏ qua kiểm tra bytecode hay cấp phép chấp nhận dữ liệu sai.

## 5. Phân biệt các nhóm lỗi

| Tình huống | Lỗi điển hình | Ý nghĩa |
| --- | --- | --- |
| Byte[] không có cấu trúc ClassFile đúng, magic sai | **ClassFormatError** | Không đọc được file theo định dạng JVM |
| Major/minor không được JVM hỗ trợ hoặc preview không tương thích | **UnsupportedClassVersionError** | JVM không chấp nhận phiên bản class file |
| Class file có cấu trúc nhưng bytecode không qua kiểm tra tính đúng đắn | **VerifyError** | Vi phạm ràng buộc kiểm chứng bytecode |
| this_class thuộc package khác lookup class; file có ACC_MODULE | **IllegalArgumentException** | Vi phạm tiền điều kiện của defineHiddenClass |
| Lookup thiếu full privilege access | **IllegalAccessException** | Không đủ quyền định nghĩa lớp ẩn |
| Sai quan hệ class/interface hoặc không liên kết được phụ thuộc | **IncompatibleClassChangeError**, **LinkageError** và các lỗi con thích hợp | Liên kết lớp thất bại |
| byte[] là null | **NullPointerException** | Tham số đầu vào không hợp lệ |

**Lưu ý về hệ phân cấp:** UnsupportedClassVersionError là một dạng **ClassFormatError**, còn ClassFormatError và VerifyError đều thuộc họ **LinkageError**. Khi cần xử lý riêng từng loại, viết các catch **từ loại cụ thể đến tổng quát**. Đây là các lớp lỗi thuộc họ **Error**, khác với exception có thể xử lý thông thường; trong chương trình sản xuất, không nên bắt chung Error chỉ để lặng lẽ tiếp tục với bytecode đã hỏng.

Bảng mô tả **nguyên nhân điển hình**, không cam kết mọi lớp bytecode hỏng đều cho cùng một loại lỗi trên mọi bước thực thi. JVM xác định lỗi phù hợp theo điều kiện vi phạm và thời điểm phát hiện.

## 6. Kiểm tra class file trước khi định nghĩa

**Cách đáng tin nhất là tạo bytecode bằng compiler hoặc một công cụ class-file có hỗ trợ phiên bản đích.** Sau đó kiểm tra tối thiểu:

1. **Môi trường chạy:** xác nhận JVM sẽ thực sự chạy ứng dụng (không chỉ phiên bản javac trên máy build).
2. **Phiên bản class file:** dùng **javap -verbose** để xem **major version** và **minor version**. Ví dụ một class biên dịch bằng --release 17 phải thể hiện major 61, minor 0.
3. **Tên/package:** xác nhận tên lớp trong this_class thuộc cùng package với lookup class.
4. **Nguồn bytecode:** chỉ dùng bytecode từ nguồn tin cậy, không xem defineHiddenClass như hộp cát bảo mật.
5. **Các ràng buộc class-file và bytecode:** để JVM xác minh; khi tự sinh bytecode, bổ sung kiểm thử với phiên bản JVM đích và đường đi thực tế của các phương thức.
6. **Dùng API đúng:** Lookup có quyền full privilege; xử lý IOException khi lấy bytecode từ resource và báo lỗi có ngữ cảnh khi thiếu class file.

Ví dụ tại terminal ở thư mục chứa class file:

~~~bash
javac --release 17 -encoding UTF-8 HiddenBytecodeVersionDemo.java
javap -verbose 'HiddenBytecodeVersionDemo$Template.class'
~~~

Dấu nháy đơn trong lệnh **javap** bảo vệ ký tự **$** ở tên class file khi dùng shell có biến môi trường hoặc biến shell; một số terminal khác dùng quy tắc quoting riêng. Phần thông tin tương ứng sẽ có **major version: 61** và **minor version: 0**. **javap** giúp quan sát định dạng và bytecode; nó **không thay thế** việc JVM kiểm chứng, liên kết và chạy lớp sinh động.

## 7. Chương trình Java 17+ hoàn chỉnh: thử đúng version và lỗi đầu vào

Chương trình sau đọc bytes của **một nested class đã được javac biên dịch**, dùng chính bytes hợp lệ đó để định nghĩa hidden class, rồi thử hai **bản sao byte[] bị sửa trong bộ nhớ**:

- **Sai magic:** biến byte đầu tiên từ **0xCA** thành **0x00**, khiến class file không hợp lệ về cấu trúc.
- **Phiên bản vượt hỗ trợ:** sửa major thành **32767** để mô phỏng một class file mang phiên bản quá mới so với JVM hỗ trợ; không thay đổi dữ liệu class file trên đĩa.

**Chỉ thao tác trên dữ liệu thử nghiệm do mình tạo**, không dùng cách sửa header này để tạo class file thật.

Lưu mã dưới đây thành **HiddenBytecodeVersionDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public class HiddenBytecodeVersionDemo {
    public static class Template {
        public static String greet() {
            return "Xin chào từ hidden class";
        }
    }

    static int unsignedShort(byte[] data, int offset) {
        return ((data[offset] & 0xff) << 8) | (data[offset + 1] & 0xff);
    }

    static byte[] readTemplate() throws IOException {
        try (InputStream in = HiddenBytecodeVersionDemo.class
                .getResourceAsStream("HiddenBytecodeVersionDemo$Template.class")) {
            if (in == null) {
                throw new IOException("Không tìm thấy class file của Template");
            }
            return in.readAllBytes();
        }
    }

    static void tryDefine(String label, byte[] bytes,
                          MethodHandles.Lookup lookup) throws IllegalAccessException {
        try {
            lookup.defineHiddenClass(bytes, false);
            System.out.println(label + ": OK");
        } catch (LinkageError | IllegalArgumentException error) {
            System.out.println(label + ": " + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = readTemplate();
        System.out.println("Class file: " + unsignedShort(bytes, 6)
                + "." + unsignedShort(bytes, 4));

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        Class<?> hidden = lookup.defineHiddenClass(bytes, true).lookupClass();
        System.out.println("Hidden: " + hidden.isHidden());
        System.out.println(hidden.getMethod("greet").invoke(null));

        byte[] badMagic = bytes.clone();
        badMagic[0] = 0;
        tryDefine("Sai magic", badMagic, lookup);

        byte[] tooNew = bytes.clone();
        tooNew[6] = (byte) 0x7f;
        tooNew[7] = (byte) 0x7f;
        tryDefine("Phiên bản vượt hỗ trợ", tooNew, lookup);
    }
}
~~~

Biên dịch và chạy tại thư mục có tệp trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 HiddenBytecodeVersionDemo.java
java HiddenBytecodeVersionDemo
~~~

**Stdout chính xác** khi dùng lệnh trên và JVM hỗ trợ Java 17:

~~~text
Class file: 61.0
Hidden: true
Xin chào từ hidden class
Sai magic: ClassFormatError
Phiên bản vượt hỗ trợ: UnsupportedClassVersionError
~~~

**Giải thích chi tiết:**

- javac sinh file **HiddenBytecodeVersionDemo$Template.class** với major **61**, minor **0** vì có **--release 17**. Resource được tìm **tương đối với package của lớp chứa chương trình**, và trong ví dụ lớp nằm ở package mặc định, chạy trong thư mục chứa các file class.
- **readTemplate()** sử dụng try-with-resources đóng InputStream và kiểm tra việc thiếu resource. Cú pháp **Class.getResourceAsStream** cũng hoạt động khi class file được đóng gói đúng vào classpath.
- **MethodHandles.lookup()** lấy quyền lookup từ lớp gọi. Vì bytecode của Template và lớp chứa main thuộc **cùng package**, điều kiện package của **defineHiddenClass** được đáp ứng.
- **defineHiddenClass(bytes, true)** định nghĩa một lớp ẩn riêng, không thay thế **Template.class**. **Class.isHidden()** trả true. Sau đó gọi public static method **greet()** bằng reflection để chứng minh hidden class chứa mã thực thi hợp lệ.
- **badMagic** là bản sao có byte đầu của header bị đổi; JVM ném **ClassFormatError**.
- **tooNew** là bản sao có major = 0x7F7F = **32639** (mức không được JVM hiện tại hỗ trợ); JVM ném **UnsupportedClassVersionError**. Mã bắt lỗi chỉ để **in tên lỗi minh họa**, không có ý nghĩa “khôi phục” bytecode hỏng.

Ví dụ đã được **biên dịch bằng javac --release 17 và chạy trên JDK 24**, đúng với stdout nêu trên. Nó không cần tùy chọn preview hoặc thư viện bên ngoài.

## 8. Lưu ý về sửa bytes và công cụ kiểm chứng

**Sửa header không đảm bảo tương thích.** Ví dụ thay version 65 (Java 21) thành 61 (Java 17) không làm các tính năng class file mới, constant-pool tag mới, lệnh bytecode hoặc metadata trở thành hợp lệ đối với Java 17. Compiler hoặc công cụ class-file phải **tạo lại nội dung tương thích thực sự**.

**Không tự tạo “hidden class file format” riêng.** Hidden class được tạo từ class file thông thường hợp lệ và được JVM cấp định danh ẩn khi gọi defineHiddenClass. Không thêm một cờ ACC_HIDDEN tùy ý hoặc ghi tên runtime có hậu tố đặc biệt vào this_class.

**Không tùy tiện dùng bytes của lớp khác package.** Dù class public và cùng class loader, điều kiện cùng package của Lookup vẫn phải được tuân thủ; nếu cần sinh lớp ở package khác, thiết kế lookup có thẩm quyền tương ứng, không sửa tên bytecode bằng chuỗi.

**Không nhầm ClassFormatError với VerifyError.** Cả hai đều liên quan đến bytecode không chấp nhận được nhưng ở những tầng khác nhau: một bên là định dạng file, một bên là tính đúng đắn của lệnh/kiểu và luồng điều khiển. Một file có header đúng vẫn có thể thất bại ở verification.

**Kiểm tra phụ thuộc lúc chạy.** Một class file có vẻ tự đủ có thể gọi method hoặc dùng class không tồn tại ở JVM đích. Khi runtime giải quyết tham chiếu, nó vẫn có thể ném lỗi liên kết. Kiểm thử các đường thực thi quan trọng và môi trường triển khai.

**Không dùng loại lỗi để suy đoán không kiểm chứng.** Khi gặp lỗi ở ứng dụng thật, ghi lại class-file major/minor, phiên bản JVM, tên/package của lookup class, công cụ sinh bytes, nguồn bytes và stack trace. So sánh những dữ liệu đó với hợp đồng API và JVMS.

## 9. Câu hỏi tự kiểm tra

**Câu 1:** Class file **61.0** tương ứng định dạng ra đời ở bản Java nào?  
**Đáp án:** Java 17.

**Câu 2:** Có thể nạp class file **65.0** (Java 21) vào JVM Java 17 bằng defineHiddenClass không?  
**Đáp án:** Không. JVM Java 17 không hỗ trợ major 65, nên có thể ném UnsupportedClassVersionError.

**Câu 3:** Class file version 61.0 và magic đúng có luôn tạo hidden class thành công không?  
**Đáp án:** Không. Còn yêu cầu cấu trúc nội bộ, bytecode hợp lệ, package, quyền Lookup và liên kết.

**Câu 4:** Tại sao không đổi minor từ 0 thành 65535 tùy ý?  
**Đáp án:** 65535 là marker preview gắn với đúng bản Java; muốn nạp cần JVM phù hợp và bật preview, đồng thời class file phải thực sự hợp lệ.

**Câu 5:** Vì sao bytes của một class nằm ở package khác không thể dùng trực tiếp với lookup hiện có?  
**Đáp án:** defineHiddenClass yêu cầu this_class của bytes có cùng package với lookup class.

**Câu 6:** Nếu JVM báo VerifyError thì chỉ sửa 8 byte header đầu có giải quyết được không?  
**Đáp án:** Không nhất thiết. VerifyError thường do nội dung và luồng điều khiển bytecode vi phạm quy tắc xác minh; cần sửa mã nguồn hoặc công cụ sinh bytecode.

## 10. Ghi nhớ

**Phiên bản class file và tính hợp lệ của bytecode là hai điều kiện riêng, đều bắt buộc.** Một hidden class được tạo qua Lookup.defineHiddenClass phải xuất phát từ một ClassFile cấu trúc đúng, có **major/minor JVM hỗ trợ**, **this_class cùng package**, **bytecode qua kiểm tra JVM**, **liên kết hợp lệ** và **Lookup đủ quyền**. 

Dùng **javac --release** để tạo bytes tương thích, **javap -verbose** để xem phiên bản, và các bài kiểm thử trên JVM mục tiêu để xác nhận hành vi. Không hạ version bằng cách sửa header hoặc cho rằng thành công của bước đọc bytes đồng nghĩa lớp đã hợp lệ.

## Tham khảo chính thức

- Oracle, **MethodHandles.Lookup.defineHiddenClass(...)**, Java SE 25: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Oracle, **JVMS §4.1 – ClassFile Structure, class file versions**, Java SE 25: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html
- Oracle, **JVMS §4.10 – Verification**, Java SE 25: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.10
- OpenJDK, **JEP 371 – Hidden Classes**: https://openjdk.org/jeps/371
