# Nạp thư viện native trong khởi tạo lớp và xử lý thất bại bằng UnsatisfiedLinkError

## Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích thời điểm JVM chạy **static initializer** và sự khác nhau giữa **nạp lớp (loading)**, **liên kết (linking)** và **khởi tạo lớp (initialization)**.
2. Viết đúng cách gọi **System.loadLibrary** trong khối **static** khi một lớp Java cần thư viện native.
3. Giải thích tại sao lỗi **UnsatisfiedLinkError** trong quá trình khởi tạo có thể làm lớp rơi vào trạng thái lỗi và vì sao những lần sử dụng tiếp theo có thể xuất hiện **NoClassDefFoundError**.
4. Phân biệt thư viện **bắt buộc** với thư viện **tùy chọn**, từ đó chọn fail-fast, xử lý lỗi có kiểm soát hoặc fallback Java hợp lệ.
5. Chẩn đoán lỗi tên thư viện, đường dẫn tìm kiếm, dependency native, kiến trúc/ABI, symbol JNI, class loader và quyền native access.
6. Kiểm thử được cả đường nạp thành công lẫn đường lỗi, không dựa vào giả định rằng bắt một exception là đủ để khôi phục lớp.

## 1. Bối cảnh: một lớp Java cần mã native

Trong Java Native Interface (JNI), lớp Java có thể khai báo phương thức **native**; phần thân được cài đặt trong thư viện mã máy dành cho hệ điều hành/CPU cụ thể. JVM phải tìm và nạp thư viện chứa phần cài đặt tương ứng trước khi các lời gọi native có thể được thực thi thành công.

Một cách viết phổ biến là:

~~~java
public final class NativeCodec {
    static {
        System.loadLibrary("example_codec");
    }

    private NativeCodec() {
    }

    public static native int decode(byte[] input);
}
~~~

Đây là **đoạn minh họa cấu trúc JNI**, chưa phải chương trình chạy độc lập: muốn gọi **decode**, cần cung cấp thư viện native thật có symbol/signature tương thích. Chuỗi **"example_codec"** là **tên logic** của thư viện, không phải một đường dẫn hay tên file DLL/SO/dylib đầy đủ.

Khi JVM **khởi tạo NativeCodec**, nó thực thi khối **static**, gọi **System.loadLibrary("example_codec")**. Nếu nạp thành công, tiến trình có thư viện sẵn để JVM liên kết phương thức native theo quy tắc JNI. Nếu thất bại và lỗi không được xử lý bên trong khối khởi tạo, **NativeCodec không được khởi tạo thành công**.

Việc đặt lệnh nạp thư viện trong static initializer có ưu điểm: tổ chức logic nạp gần với lớp cần native code, tránh gọi nạp lặp trước mỗi thao tác. Tuy nhiên, nó cũng tạo ra một ràng buộc quan trọng: **lỗi ở thời điểm khởi tạo có thể khiến toàn bộ lớp không sử dụng tiếp được trong class loader hiện tại**.

## 2. Khi nào khối static được thực thi?

Cần phân biệt ba bước trong vòng đời lớp:

| Bước | Ý nghĩa | Có đồng nghĩa chạy static initializer? |
| --- | --- | --- |
| **Loading** | Class loader tìm/định nghĩa biểu diễn của lớp | Không |
| **Linking** | Verify, prepare và có thể resolve tham chiếu | Không |
| **Initialization** | Chạy bộ khởi tạo các trường static và các khối static theo thứ tự khai báo | **Có** |

Theo Java Language Specification (JLS §12.4), khởi tạo thường diễn ra ngay trước **lần sử dụng chủ động đầu tiên** của lớp, ví dụ tạo đối tượng, gọi phương thức static được khai báo bởi lớp, ghi trường static hoặc đọc trường static không phải compile-time constant. Một số thao tác phản chiếu cũng kích hoạt khởi tạo.

Ví dụ:

~~~java
final class Demo {
    static final String CONSTANT = "ready"; // compile-time constant
    static int counter = initCounter();

    private static int initCounter() {
        System.out.println("Demo initialized");
        return 1;
    }

    static void run() {
    }
}
~~~

Đoạn trên là lớp hỗ trợ minh họa, có thể dùng từ một lớp main khác. Tham chiếu **Demo.CONSTANT** từ code được biên dịch thông thường **không buộc JVM khởi tạo Demo**, vì trường này là compile-time constant. Trái lại, gọi **Demo.run()** hoặc đọc **Demo.counter** kích hoạt initialization nếu nó chưa diễn ra.

Các thao tác như **Demo.class** hoặc **Class.forName("Demo", false, loader)** không nhất thiết kích hoạt initialization. **Class.forName("Demo")** mặc định yêu cầu khởi tạo. Do đó, câu “thư viện được nạp khi file .class được đọc vào bộ nhớ” là **không chính xác**; lệnh nạp trong static initializer chạy khi lớp **được khởi tạo**.

### Thứ tự và tính đồng bộ

- Bộ khởi tạo trường static và khối static chạy theo thứ tự văn bản được quy định; superclass cần thiết được khởi tạo trước subclass.
- JVM phối hợp các luồng đồng thời yêu cầu khởi tạo **cùng một lớp**, nên hai thread không tự ý chạy hai lần một static initializer thành công của cùng lớp.
- Đơn vị định danh lớp tại runtime gồm **tên lớp và defining class loader**. Với một lớp đã khởi tạo thành công, khối static không chạy lại trong cùng định danh runtime đó.

Những điều này giúp static initializer phù hợp cho phần khởi tạo nhỏ, xác định được kết quả, nhưng cũng làm lỗi khởi tạo trở nên đặc biệt nghiêm trọng.

## 3. System.loadLibrary và System.load

Cả hai API đều dùng để nạp mã native vào tiến trình JVM, nhưng nhận tham số khác nhau:

| API | Đầu vào | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **System.loadLibrary(String libname)** | Tên thư viện logic, không gồm path, tiền tố theo nền tảng hoặc phần mở rộng | **System.loadLibrary("codec")** | JVM/loader ánh xạ tên và tìm theo cơ chế native library search |
| **System.load(String filename)** | Đường dẫn tuyệt đối tới thư viện native | **System.load(absolutePath)** | Phù hợp khi ứng dụng quản lý chính xác artifact/path; vẫn phải xử lý dependency |

Trên các nền tảng thông dụng, **System.mapLibraryName("codec")** có thể tạo tên kiểu **codec.dll**, **libcodec.so** hoặc **libcodec.dylib**. Kết quả thực tế tùy JVM và nền tảng; không tự hardcode một tên file cho tất cả hệ điều hành.

**Ví dụ cấu hình khi chạy JVM:**

~~~bash
java -Djava.library.path=/opt/app/native MyApplication
~~~

Đây là cách cấu hình đường dẫn tìm kiếm ở lúc khởi động trong môi trường thích hợp; trên Windows hãy dùng đường dẫn Windows. Việc thay đổi thuộc tính **java.library.path** sau khi JVM đã khởi động **không được xem là cách đáng tin cậy** để buộc bộ loader tìm lại thư viện. Ngoài ra, OS loader còn cần tìm được **các dependency của chính thư viện native**, vốn không nhất thiết được giải quyết chỉ bằng java.library.path.

**Không truyền đường dẫn vào loadLibrary:** **System.loadLibrary("/opt/app/native/libcodec.so")** là dùng sai hợp đồng. Nếu đã có đường dẫn tuyệt đối được kiểm chứng, dùng **System.load**.

## 4. Lỗi UnsatisfiedLinkError phát sinh ở đâu?

**UnsatisfiedLinkError** là lớp con của **LinkageError**, mà **LinkageError** là lớp con của **Error**. Nó biểu thị rằng JVM không thể thỏa mãn một yêu cầu liên kết/native linkage trong tình huống tương ứng.

Có nhiều nhóm nguyên nhân:

| Thời điểm | Nguyên nhân điển hình | Gợi ý xác minh |
| --- | --- | --- |
| **Khi gọi loadLibrary** | Không tìm được file, sai tên logic, sai đường tìm kiếm | Tên truyền vào API, giá trị java.library.path, vị trí binary |
| **Khi loader mở binary** | Sai OS/CPU/ABI, file native hỏng hoặc dependency bị thiếu | Kiến trúc JVM và binary, danh sách thư viện phụ thuộc, libc/runtime |
| **Khi class loader quản lý library** | Cùng thư viện JNI bị nạp vào hai class loader không tương thích theo quy tắc JNI | Cấu trúc class loader và nơi khai báo JNI adapter |
| **Khi phương thức native được liên kết/sử dụng** | Không tìm thấy implementation/symbol JNI khớp chữ ký Java | Java native declaration, export symbol, signature, bản build |
| **Khi khởi tạo native** | Thư viện hoặc hàm khởi tạo JNI trả lỗi / không hoàn tất đúng hợp đồng | Native loader log, JNI_OnLoad, dependency và crash report |

**Nạp được file không bảo đảm mọi phương thức native đều gọi được.** Chẳng hạn, **System.loadLibrary("codec")** có thể thành công nhưng khi gọi **nativeDecode(...)** JVM vẫn phát sinh **UnsatisfiedLinkError** vì thiếu hoặc sai implementation. Vì thế **“load success” ≠ “native feature readiness”**: một smoke test có kiểm soát hoặc kiểm thử tích hợp thực tế vẫn cần thiết.

Ngược lại, không phải mọi thất bại đều là UnsatisfiedLinkError. Một đối số null có thể gây **NullPointerException**; chính sách kiểm soát truy cập có thể sinh **SecurityException** hoặc **IllegalCallerException** theo phiên bản/cấu hình JDK; native code lỗi nghiêm trọng có thể crash toàn tiến trình mà Java không thể bắt để phục hồi.

## 5. Điều gì xảy ra khi loadLibrary thất bại ngay trong static initializer?

Xem mẫu tối giản:

~~~java
final class RequiredNative {
    static {
        System.loadLibrary("required_native");
    }

    static void use() {
        System.out.println("Ready");
    }
}
~~~

Giả sử thư viện **required_native** không tồn tại hoặc không được nạp thành công:

1. Lần đầu gọi **RequiredNative.use()** yêu cầu JVM khởi tạo RequiredNative.
2. JVM chạy khối static, **System.loadLibrary** ném **UnsatisfiedLinkError**.
3. Lỗi không được bắt trong static initializer nên quá trình initialization **kết thúc bất thường**.
4. JVM đánh dấu RequiredNative ở trạng thái **erroneous** trong class loader hiện tại.
5. Lời gọi lần đầu có thể trả ra **UnsatisfiedLinkError** ban đầu.
6. Lần sử dụng chủ động tiếp theo của **cùng lớp đã lỗi** sẽ không chạy lại static initializer; JVM phát sinh **NoClassDefFoundError** cho việc không thể khởi tạo lớp đó.

Điểm số 6 là nguồn gây hiểu nhầm phổ biến. **NoClassDefFoundError không phải lúc nào cũng có nghĩa thiếu file .class**. Nó cũng có thể là hậu quả của **một lần khởi tạo lớp đã thất bại trước đó**. Phải tìm **lỗi gốc đầu tiên**, thường nằm ở log sớm hơn hoặc trong cause chain.

### Phân biệt ba loại lỗi

| Lỗi quan sát được | Ý nghĩa trong trường hợp này |
| --- | --- |
| **UnsatisfiedLinkError** | JVM không nạp/liên kết được thư viện hoặc phương thức native; có thể là lỗi gốc xảy ra trong static initializer |
| **ExceptionInInitializerError** | JVM bọc một throwable **không phải Error** thoát ra khỏi static initializer, ví dụ RuntimeException; xem **getCause()** |
| **NoClassDefFoundError** | Trong lần dùng sau, JVM phát hiện lớp đang ở trạng thái erroneous do khởi tạo trước đó thất bại |

Theo JLS §12.4.2, nếu throwable từ initializer đã là **Error** hoặc lớp con của Error thì JVM **không bọc nó trong ExceptionInInitializerError**. Vì **UnsatisfiedLinkError extends Error**, lỗi này thường thoát ra trực tiếp ở lần khởi tạo đầu tiên. Một **IllegalCallerException** không được xử lý trong static initializer lại có thể bị bọc thành **ExceptionInInitializerError**. Không nên mặc định tất cả lỗi static đều có chung kiểu exception.

### Vì sao không thể “thử lại” bằng cách gọi lớp lần nữa?

Vì class đã bị đánh dấu erroneous. Dù sau đó thư viện native được chép vào đúng thư mục, **lớp đã thất bại vẫn không tự khởi tạo lại trong cùng class loader**. Trong ứng dụng thông thường, cách phục hồi đáng tin cậy là sửa cấu hình/binary rồi **khởi động lại tiến trình**. Một cơ chế nạp lại bằng class loader mới chỉ nên dùng khi hệ thống đã thiết kế đúng cho reload và quy tắc ownership của JNI library.

## 6. Ví dụ Java 17+ chạy độc lập: so sánh fail-fast và fallback

Ví dụ này **không cần thư viện C/JNI thực sự** để kiểm tra hành vi của JVM. Tham số **demo.simulateMissing=true** khiến hàm helper ném chính loại **UnsatisfiedLinkError** mà lời gọi nạp thư viện có thể phát sinh. Khi tắt mô phỏng, helper mới gọi **System.loadLibrary** thật.

Tạo file **NativeInitLesson.java**:

~~~java
public final class NativeInitLesson {
    private NativeInitLesson() {
    }

    private static void attemptLoad() {
        if (Boolean.getBoolean("demo.simulateMissing")) {
            throw new UnsatisfiedLinkError("Simulated missing native library");
        }
        System.loadLibrary("lesson_native_42");
    }

    // Thư viện bắt buộc: lỗi nạp thoát ra khỏi static initializer.
    private static final class Required {
        static {
            attemptLoad();
        }

        static String state() {
            return "native loaded";
        }
    }

    // Thư viện tùy chọn: chỉ bắt lỗi nạp đã được dự kiến.
    private static final class Optional {
        static final boolean LOADED;
        static final String LOAD_STATUS;

        static {
            boolean loaded;
            String status;
            try {
                attemptLoad();
                loaded = true;
                status = "loaded";
            } catch (UnsatisfiedLinkError error) {
                loaded = false;
                status = error.getClass().getSimpleName();
            }
            LOADED = loaded;
            LOAD_STATUS = status;
        }

        static String mode() {
            return LOADED ? "native candidate" : "java fallback";
        }
    }

    public static void main(String[] args) {
        for (int i = 1; i <= 2; i++) {
            try {
                System.out.println("Required #" + i + ": " + Required.state());
            } catch (UnsatisfiedLinkError | NoClassDefFoundError error) {
                System.out.println(
                    "Required #" + i + ": "
                    + error.getClass().getSimpleName()
                );
            }
        }

        System.out.println("Optional: " + Optional.mode());
        System.out.println("Optional load status: " + Optional.LOAD_STATUS);
    }
}
~~~

Chạy với **JDK 17 trở lên**:

~~~bash
javac NativeInitLesson.java
java -Ddemo.simulateMissing=true NativeInitLesson
~~~

**Stdout chính xác của chế độ mô phỏng:**

~~~text
Required #1: UnsatisfiedLinkError
Required #2: NoClassDefFoundError
Optional: java fallback
Optional load status: UnsatisfiedLinkError
~~~

### Phân tích kết quả

- **Required #1**: câu lệnh gọi phương thức static của lớp Required kích hoạt initialization; lỗi UnsatisfiedLinkError thoát ra, khiến Required ở trạng thái erroneous.
- **Required #2**: JVM không chạy lại static initializer. Nó trả về NoClassDefFoundError cho việc dùng lớp Required đã khởi tạo thất bại.
- **Optional**: khối static **bắt riêng UnsatisfiedLinkError**, điền hai trường static và kết thúc bình thường. Vì thế lớp Optional **đã khởi tạo thành công** và có thể trả trạng thái fallback.
- **Optional.LOAD_STATUS** cho biết phân loại lỗi, nhưng không cố định một chuỗi stack trace hoặc message phụ thuộc nền tảng.

Dòng **Optional: java fallback** chỉ mô tả **quyết định điều hướng**. Ví dụ không triển khai một thuật toán native cụ thể; trong hệ thống thật, chỉ dùng fallback khi thuật toán Java thay thế có **ngữ nghĩa tương đương được kiểm chứng**, bao gồm mã lỗi, độ chính xác, encoding, tác động phụ và yêu cầu bảo mật.

**Tại sao dùng mô phỏng?** Nó cho ra cùng một kết quả trên Windows, Linux và macOS, kể cả khi máy đã cài sẵn nhiều thư viện. Chạy mà không có thuộc tính **demo.simulateMissing** sẽ thử tìm library **lesson_native_42** thật; kết quả khi đó phụ thuộc môi trường và trạng thái native access của JDK.

**Quan trọng:** Hai nhánh **catch (UnsatisfiedLinkError | NoClassDefFoundError)** trong **main** chỉ phục vụ quan sát khác biệt lỗi. Khi viết ứng dụng thật, không nên bắt NoClassDefFoundError tràn lan để che lỗi triển khai Java hoặc lỗi classpath.

## 7. Chọn chiến lược: thư viện bắt buộc hay tùy chọn?

Không nên dùng một chiến lược bắt lỗi cho mọi module native. Hãy xác định rõ kỳ vọng sản phẩm trước khi viết static initializer.

### 7.1. Thư viện bắt buộc: fail-fast có thông tin

Nếu một tính năng cốt lõi hoàn toàn phụ thuộc native, không nên giả vờ ứng dụng đã sẵn sàng khi library không nạp được.

~~~java
final class MandatoryEngine {
    static {
        System.loadLibrary("mandatory_engine");
    }

    static void checkAvailable() {
        // Gọi khi bootstrap để buộc lớp được khởi tạo sớm.
    }
}
~~~

Đây là **đoạn minh họa**, yêu cầu binary **mandatory_engine** thật. Nếu không có library, lỗi từ static initializer giúp ngăn lớp được dùng ở trạng thái sai.

Tuy nhiên, static initializer chỉ chạy ở **lần active use đầu tiên**, vốn có thể xảy ra muộn trong request production. Với thư viện bắt buộc, nên **gọi health check hoặc thao tác khởi tạo có chủ đích tại startup**, trước khi báo service READY. Khi lỗi, log đủ thông tin chẩn đoán rồi dừng startup, thay vì để request đầu tiên phát hiện lỗi.

Nếu cần thông điệp nghiệp vụ rõ ràng, xử lý và bổ sung thông tin **ở ranh giới bootstrap**, đồng thời giữ lại lỗi gốc trong log/cause. Tránh chuyển mọi lỗi thành một câu chung “JNI failed” khiến mất dấu nguyên nhân.

### 7.2. Thư viện tùy chọn: catch trong initializer và ghi nhận trạng thái

Nếu native chỉ là tăng tốc một khả năng đã có cách Java tương đương, có thể bắt **UnsatisfiedLinkError** ngay trong phần khởi tạo. Khi catch thành công và static initializer kết thúc bình thường, lớp không bị đánh dấu erroneous.

Để pattern này an toàn:

1. Chỉ bắt lỗi đã dự kiến trong **phạm vi lệnh nạp**; không đặt quá nhiều logic khởi tạo unrelated bên trong cùng khối try.
2. Lưu trạng thái **available / unavailable** và lý do cho telemetry; không lặp lại lệnh nạp vô hạn khi mỗi request chạy tới.
3. Đảm bảo API ngoài **không gọi phương thức native** nếu nhánh unavailable.
4. Nếu load thành công nhưng cần gọi native method, **kiểm chứng riêng symbol và hành vi**. Một cờ LOADED chỉ chứng minh bước nạp library, không chứng minh toàn bộ chức năng đã sẵn sàng.
5. Chỉ fallback khi hợp đồng Java/native tương đương; nếu tính năng bắt buộc hoặc thiếu tương đương, trả trạng thái lỗi rõ ràng.

Một lỗi nạp thư viện do sai cấu hình production có thể cần báo **UNHEALTHY** ngay cả khi có fallback Java, tùy yêu cầu SLO và tính đúng. Tránh nuốt lỗi rồi âm thầm chạy chậm hơn hoặc thay đổi kết quả mà không quan sát được.

### 7.3. Trì hoãn nạp bằng lớp Holder

Khi chỉ một tính năng phụ cần native, hãy giữ phần còn lại của ứng dụng độc lập với lớp nạp thư viện. Có thể đặt cơ chế nạp trong **nested static holder**, sau đó truy cập holder **chỉ khi** tính năng được bật.

Lợi ích: tránh việc một class khởi tạo sớm làm yêu cầu native xuất hiện ở mọi luồng bootstrap. Nhưng **lazy loading không giải quyết khả năng retry**: nếu chính holder có static initializer thất bại, holder cũng trở thành erroneous. Kết hợp holder với cơ chế báo trạng thái và phân loại bắt lỗi theo chiến lược đã chọn.

### 7.4. Vì sao không nên catch Error hoặc Throwable vô điều kiện?

**Error** còn bao gồm các tình huống nghiêm trọng như **OutOfMemoryError** và các lỗi liên kết khác. Bắt rộng và giả vờ tiếp tục thường làm che hỏng trạng thái tiến trình. Chỉ nên bắt **đúng lỗi mà adapter có thể xử lý**; trong phạm vi nạp thư viện tùy chọn đó có thể là UnsatisfiedLinkError. Một lỗi khác như **IllegalCallerException** do chính sách native access phải được đánh giá riêng, không mặc định xem tương đương “library missing”.

## 8. Chẩn đoán lỗi nạp native theo thứ tự

Khi gặp lỗi trong startup hoặc lúc dùng tính năng, hãy xác định **lần đầu lỗi phát sinh**, ghi lại chuỗi cause và xác định bước thất bại.

### Bước 1 — Xác minh API, tên và thời điểm

- Đang gọi **System.loadLibrary** hay **System.load**?
- Nếu dùng loadLibrary, tên có đúng **tên logic không path/extension**?
- Nếu dùng load, đường dẫn có **tuyệt đối**, file có thực sự tồn tại và tiến trình có quyền truy cập?
- Lỗi xảy ra ngay tại static initializer, hay sau khi load thành công và **gọi native method**?
- Log đầu tiên là UnsatisfiedLinkError, nhưng lần đọc log hiện tại chỉ còn NoClassDefFoundError? Hãy tìm nguyên nhân **trước thời điểm lớp bị erroneous**.

### Bước 2 — Kiểm tra nền tảng của JVM và binary

Ghi nhận OS, **os.arch**, phiên bản Java, Java vendor/runtime, CPU và artifact native đã được chọn. Một JVM 64-bit không nạp trực tiếp binary 32-bit không tương thích; binary Windows không thể được nạp như shared object Linux.

Lưu ý rằng **os.arch** là thuộc tính hữu ích để chẩn đoán, không thay thế việc kiểm tra định dạng binary/ABI thật. Với Linux, sự khác biệt glibc/musl hoặc phiên bản dependency cũng quan trọng.

### Bước 3 — Kiểm tra dependency bậc hai

Thư viện được trỏ tới có thể tồn tại nhưng chính nó cần thư viện khác không có trong runtime. Tùy nền tảng, có thể dùng các công cụ hệ điều hành phù hợp:

| Hệ điều hành | Kiểm tra thường dùng |
| --- | --- |
| Linux | **file**, **readelf**, **ldd** trong môi trường đáng tin cậy |
| macOS | **file**, **otool -L** |
| Windows | Công cụ kiểm tra dependency/DLL và PE architecture tương ứng |

Không chạy **ldd** với binary không đáng tin cậy; hãy dùng công cụ kiểm tra tĩnh phù hợp. Thực hiện kiểm tra trên **đúng container/server image** đang gặp lỗi, không chỉ trên máy phát triển.

### Bước 4 — Kiểm tra symbol và hợp đồng JNI

Nếu nạp library thành công nhưng lời gọi native vẫn không liên kết, kiểm tra:

- Native method có được khai báo đúng tên, kiểu tham số, kiểu trả về và static/instance theo JNI không?
- Symbol tương ứng có được export? Có sai name mangling, overload, package hoặc tên lớp không?
- Header JNI được sinh từ đúng bản Java source chưa? Có đang triển khai một version cũ của lớp không?
- Có yêu cầu đăng ký native method bằng **RegisterNatives** nhưng đường đăng ký không chạy hoặc sai signature không?

Thông báo “method not found” cần được phân biệt với “file not found”; đổi java.library.path không sửa được một symbol JNI bị thiếu.

### Bước 5 — Kiểm tra class loader

Trong application server, hệ thống plugin hoặc hot reload, cùng JNI library có thể bị hai class loader riêng cố nạp. Đặc tả JNI quy định mỗi class loader quản lý tập native library của mình; **cùng một JNI native library không thể nạp vào hai class loader độc lập**, nếu cố làm sẽ gây UnsatisfiedLinkError.

Giải pháp là thiết kế nơi đặt adapter/library và lifecycle class loader nhất quán. Không tạo bản sao cùng binary ở đường dẫn khác như một cách “né” giới hạn khi chưa hiểu rủi ro state toàn cục của thư viện.

### Bước 6 — Kiểm tra native access theo JDK

Từ **JDK 24**, thao tác nạp/ liên kết JNI thuộc cơ chế restricted native access. Theo cấu hình JDK, thao tác thiếu quyền có thể gây cảnh báo hoặc **IllegalCallerException**. Tùy môi trường:

~~~bash
java --enable-native-access=ALL-UNNAMED MyApplication
~~~

Dùng **ALL-UNNAMED** khi adapter nằm trên classpath; nếu ứng dụng modularized, ưu tiên cấp cho **module cụ thể**. Trên các JDK hỗ trợ tùy chọn **--illegal-native-access=deny**, có thể dùng trong môi trường test để phát hiện chỗ chưa khai báo quyền. Không bật quyền một cách mù quáng nhằm “sửa mọi UnsatisfiedLinkError”: lỗi thiếu binary hay sai ABI vẫn cần khắc phục riêng.

### Bước 7 — Phân biệt lỗi Java có thể bắt với crash native

Native code có thể làm hỏng bộ nhớ hoặc khiến tiến trình crash, vượt ngoài khả năng của try/catch Java. Nếu có crash JVM hoặc lỗi off-heap, thu thập crash log, native stack, file symbol phù hợp và chẩn đoán bằng profiler/sanitizer native. Bắt UnsatisfiedLinkError chỉ xử lý một nhóm lỗi nạp/liên kết, **không tạo lớp bảo vệ memory safety** cho thư viện C/C++.

## 9. Tình huống thực tế và quyết định xử lý

### Tình huống A — Production thiếu thư viện bắt buộc

Service chỉ thực hiện được chức năng lõi khi có **libcriticalcodec**. Khởi động JVM thành công nhưng request đầu tiên gọi lớp JNI mới phát sinh UnsatisfiedLinkError, rồi các request sau thấy NoClassDefFoundError.

**Cách làm:** buộc một thao tác kiểm tra adapter tại bootstrap; xác minh file và dependency trong image; dừng startup với thông tin lỗi gốc nếu không đạt. Không retry bằng cách gọi lại cùng class đã erroneous.

### Tình huống B — Bộ tăng tốc native chỉ có ở Linux

Một phép toán Java thuần vẫn chạy đúng trên Windows. Linux có bản native giúp tăng tốc.

**Cách làm:** đặt adapter native trong vùng được truy cập có điều kiện, catch lỗi nạp dự kiến trong initializer, ghi trạng thái và dùng đường Java tương đương đã test. Kiểm soát feature flag và metrics để biết có bao nhiêu request dùng nhánh nào. Nếu load thành công, chạy smoke test để xác nhận native symbol thực sự hoạt động.

### Tình huống C — Hot reload tạo class loader mới

Sau khi triển khai lại plugin, một class loader mới cố gọi System.loadLibrary với thư viện JNI đã được quản lý bởi loader cũ.

**Cách làm:** xem lại ranh giới class loader và lifecycle native library; có thể cần đặt adapter ở class loader chia sẻ hoặc yêu cầu restart dịch vụ thay vì hot reload. Không mặc định rằng việc đổi path file sẽ giải quyết vấn đề ownership của JNI.

### Tình huống D — CI pass, container production fail

CI chạy trên glibc x86-64, image production dùng biến thể libc khác hoặc ARM64. File library xuất hiện đúng đường dẫn nhưng loader báo không thể nạp.

**Cách làm:** build và smoke test theo **OS × architecture × ABI/libc**; kiểm tra dependency bậc hai của image thực, không chỉ đường dẫn file. Giữ artifact version/checksum để biết bản native nào đi cùng bản JAR.

## 10. Cách kiểm thử có ý nghĩa

Một bài test chỉ gọi **System.mapLibraryName** không kiểm tra được library có nạp thành công. Với hệ thống có JNI thực, nên có các tầng kiểm tra sau:

1. **Unit test Java:** mô phỏng loader báo UnsatisfiedLinkError để xác minh state transition; bài ví dụ runnable ở mục 6 kiểm tra được lỗi first/second use của static initializer.
2. **Bootstrap test bắt buộc:** cấu hình thiếu thư viện, khẳng định service không báo READY và log giữ nguyên nguyên nhân gốc.
3. **Optional-fallback test:** thiếu thư viện nhưng lớp optional vẫn khởi tạo bình thường, API trả kết quả đúng hợp đồng Java; không bị NoClassDefFoundError khi gọi lại.
4. **Native smoke test thật:** có binary đúng nền tảng, gọi một phương thức native nhỏ, kiểm tra symbol, kết quả và quy tắc ownership.
5. **Packaging test:** chạy trên từng image/CPU/ABI được hỗ trợ, gồm dependency bậc hai; không chỉ trên máy của người phát triển.
6. **Concurrency test:** nhiều thread cùng kích hoạt lần active use đầu tiên; bảo đảm không có trạng thái thành công giả hay lỗi khó chẩn đoán.
7. **Upgrade test:** thay version native và Java adapter, kiểm tra ABI, native access flags và khả năng rollback/restart.

Một lỗi từ static initializer có thể ảnh hưởng toàn bộ vòng đời của lớp; khi chạy test khác nhau trong **cùng JVM và cùng class loader**, đừng trông đợi việc “setup lại file DLL/SO” sẽ làm class erroneous được khởi tạo lại. Tổ chức test độc lập bằng process hoặc class loader phù hợp với tình huống.

## 11. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi **System.loadLibrary("libfoo.so")** | Nhầm tên logic với tên file nền tảng | Truyền **"foo"** nếu file/loader tuân theo cách ánh xạ đó |
| Đặt load trong static rồi cho rằng startup luôn phát hiện lỗi | Lớp có thể chỉ initialized tại request đầu tiên | Gọi bootstrap check có chủ đích với library bắt buộc |
| Catch UnsatisfiedLinkError **chỉ ở caller** và thử lại cùng class | Lần sau gặp **NoClassDefFoundError** vì class erroneous | Xử lý tại initializer cho library tùy chọn hoặc restart cho library bắt buộc |
| Catch **Throwable** rồi bỏ qua | Che cả lỗi nghiêm trọng và thiếu trạng thái kiểm soát | Bắt lỗi cụ thể, phân loại fail-fast/fallback |
| Chỉ đánh dấu READY khi **loadLibrary** thành công | JNI symbol hoặc native method vẫn có thể sai | Thêm native integration smoke test |
| “Sửa” bằng cách đổi **java.library.path** lúc runtime | Loader không nhất thiết cập nhật search state | Cấu hình đúng trước startup; dùng absolute path khi thực sự cần |
| Chỉ kiểm tra file chính tồn tại | Có thể thiếu libc/C++ runtime hoặc dependency khác | Kiểm tra chain dependency và ABI |
| Đổi tên file cùng JNI library và nạp qua nhiều loader | Xung đột JNI lifecycle, state global nguy hiểm | Thiết kế class-loader ownership chuẩn |
| Mọi lỗi native đều bị xem là UnsatisfiedLinkError | Có SecurityException, IllegalCallerException, crash, lỗi nghiệp vụ | Chẩn đoán dựa trên loại lỗi và giai đoạn thực thi |

## 12. Checklist dành cho người triển khai

- [ ] Đã xác định native library là **bắt buộc** hay **tùy chọn**.
- [ ] Đã chọn thời điểm active use và hiểu khi nào **static initializer** chạy.
- [ ] Đã phân biệt **System.loadLibrary** (tên logic) và **System.load** (đường dẫn tuyệt đối).
- [ ] Đã xác minh binary và toàn bộ dependency trên từng OS/CPU/ABI/container được hỗ trợ.
- [ ] Đã thiết kế xử lý **UnsatisfiedLinkError** ở đúng vị trí; không vô tình để class optional thành erroneous.
- [ ] Đã hiểu lỗi lần đầu và **NoClassDefFoundError** lần sau; log giữ được lỗi gốc.
- [ ] Đã tách **load success** khỏi **native method/link success** bằng smoke test.
- [ ] Đã kiểm tra quyền native access khi dùng JDK có cơ chế restricted native access.
- [ ] Đã quyết định rõ chế độ fail startup hoặc fallback có ngữ nghĩa tương đương.
- [ ] Đã thử lỗi trên môi trường giống production và lên phương án restart/rollback.
- [ ] Đã ghi lại phiên bản Java, native artifact và bối cảnh lỗi phục vụ vận hành.

## 13. Tự kiểm tra kiến thức

**Câu 1.** Một lớp có khối static gọi System.loadLibrary. Khi chỉ tham chiếu **SomeNativeClass.class**, lệnh nạp có nhất thiết chạy chưa?

**Trả lời:** Chưa. Tham chiếu class literal không tự buộc initialization. Lệnh nạp nằm trong static initializer nên chạy khi quá trình khởi tạo thực sự diễn ra.

**Câu 2.** Lần đầu gọi một lớp thất bại với UnsatisfiedLinkError; lần sau nhận NoClassDefFoundError. Có phải class file bị xóa giữa hai request?

**Trả lời:** Không thể kết luận như vậy. Khả năng rất quan trọng là class đã bị đánh dấu erroneous vì lần initialization đầu thất bại; JVM không thử chạy lại khối static của class đó.

**Câu 3.** Vì sao UnsatisfiedLinkError trong static initializer thường không trở thành ExceptionInInitializerError?

**Trả lời:** Nó là một **Error**. JLS chỉ bọc throwable không thuộc Error vào ExceptionInInitializerError trong bước xử lý lỗi initializer.

**Câu 4.** Catch UnsatisfiedLinkError trong static initializer có đảm bảo native feature dùng được chưa?

**Trả lời:** Không. Nó chỉ giúp lớp optional hoàn thành initialization khi đã chọn fallback. Nếu bước load thành công thì việc liên kết symbol/call native vẫn cần kiểm chứng; nếu fallback thì cần đảm bảo tương đương nghiệp vụ.

**Câu 5.** Có thể sửa file native rồi gọi lại lớp đã erroneous để thử nạp lại không?

**Trả lời:** Không trong cùng định danh class loader đã thất bại. Cần sửa môi trường và dùng lifecycle nạp mới, thông thường là restart; reload class loader mới phải phù hợp quy tắc JNI.

## Tài liệu chính thức

- [Java Language Specification §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.4).
- [Java SE 21 System.loadLibrary và System.load](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#loadLibrary(java.lang.String)).
- [Java Native Interface — Library and Version Management](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html).
- [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472).

**Kết luận cần ghi nhớ:** Đặt **System.loadLibrary** trong static initializer là một mô hình phổ biến và hợp lý khi lớp cần JNI, nhưng **lỗi không xử lý được làm thất bại initialization**. Với thư viện bắt buộc, hãy fail-fast tại startup và giữ lỗi gốc. Với thư viện tùy chọn, xử lý UnsatisfiedLinkError trong initializer, hoàn tất trạng thái lớp và chỉ fallback khi có bảo đảm tương đương. Luôn phân biệt **lỗi nạp lần đầu** với **NoClassDefFoundError khi dùng lại lớp đã erroneous**.
