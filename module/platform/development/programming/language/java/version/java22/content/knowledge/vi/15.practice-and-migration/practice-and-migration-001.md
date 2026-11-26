# Lập bảng tính năng theo JDK: nguồn gốc Java 22, trạng thái hiện tại và tùy chọn chạy

> **Mốc đối chiếu: 24/11/2026.** JDK 27 là bản feature release mới nhất; JDK 25 là bản LTS mới nhất. Bài này rà soát những tính năng có mặt trong JDK 22 và vẫn còn giá trị sử dụng trên các JDK hiện đại. Trạng thái preview/incubator được đối chiếu đến JDK 27.

Java 22 phát hành ngày 19/03/2024. Đây là bản feature release sáu tháng, không phải LTS. Theo lộ trình hỗ trợ Java SE của Oracle, vòng hỗ trợ JDK 22 kết thúc vào tháng 09/2024; nhà cung cấp JDK khác có thể có chính sách riêng. Vì vậy, hãy xem Java 22 là mốc lịch sử để tra cứu tính năng, còn JDK 25 hoặc JDK 27 mới là lựa chọn runtime cần cân nhắc hiện nay.

Một JEP xuất hiện trong Java 22 không có nghĩa tính năng đó đã ổn định. Có tính năng đã final ngay ở JDK 22, có tính năng hoàn tất sau vài bản preview, và có API vẫn đang incubate. Cần phân biệt trạng thái này trước khi chọn cờ biên dịch và chạy chương trình.

## 1. Phân biệt trạng thái tính năng

| Trạng thái | Ý nghĩa | Cách sử dụng |
|---|---|---|
| **Final / permanent** | Đặc tả và API đã trở thành phần ổn định của Java SE. | Dùng trực tiếp trên JDK có phiên bản giới thiệu tính năng trở đi; không cần cờ preview. |
| **Preview** | Thiết kế đã đủ để thử nghiệm nhưng có thể đổi hoặc bị rút ở bản sau. | Bật preview khi biên dịch và khi chạy; dùng cùng phiên bản JDK cho cả hai bước. |
| **Incubator** | API đang được thử nghiệm trong module riêng; hình dạng API có thể thay đổi. | Thêm module incubator bằng **--add-modules**; không đồng nhất incubator với preview. |
| **Thay đổi runtime** | Cải tiến bên trong JVM, GC hoặc launcher, không thêm cú pháp/API mà ứng dụng phải gọi. | Thường được áp dụng tự động khi dùng đúng runtime hoặc thành phần liên quan. |

Một số tính năng được preview lần đầu từ JDK 21 hoặc sớm hơn, rồi tiếp tục preview trong JDK 22. Vì vậy, cột Java 22 bên dưới ghi lại trạng thái của tính năng tại JDK 22, không khẳng định Java 22 luôn là nơi tính năng xuất hiện lần đầu.

## 2. Bảng trạng thái các tính năng Java 22 còn áp dụng

| JEP tại Java 22 | Tính năng và giá trị sử dụng | Trạng thái đến JDK 27 | Tùy chọn chạy hiện nay |
|---|---|---|---|
| [423](https://openjdk.org/jeps/423) | **Region Pinning for G1** — G1 có thể tiếp tục thu gom các vùng heap khác trong khi một số đối tượng cần được giữ nguyên địa chỉ trong JNI critical region. | Đã tích hợp từ JDK 22; vẫn là hành vi của G1. JDK 27 đặt G1 làm GC mặc định trong mọi môi trường qua [JEP 523](https://openjdk.org/jeps/523). | Không có cờ riêng cho region pinning. Dùng G1 bình thường; chỉ cần **-XX:+UseG1GC** nếu muốn chọn G1 một cách tường minh. |
| [447](https://openjdk.org/jeps/447) | **Statements Before super(...)** — cho phép kiểm tra tham số, tính toán đối số hoặc khởi tạo field trước lời gọi constructor tường minh. | Preview ở JDK 22; trở thành tính năng ổn định trong JDK 25 qua [JEP 513](https://openjdk.org/jeps/513), tên mới là *Flexible Constructor Bodies*. | Không cần **--enable-preview** trên JDK 25+. |
| [454](https://openjdk.org/jeps/454) | **Foreign Function & Memory API (FFM)** — gọi hàm native và thao tác vùng nhớ ngoài heap với API Java có cấu trúc. | Final ngay trong JDK 22; tiếp tục có trong JDK 27. | Không cần preview hoặc thêm module. Khi gọi các restricted methods để nạp/liên kết thư viện native, bật native access bằng **--enable-native-access=ALL-UNNAMED** cho classpath hoặc tên module cụ thể cho module path. |
| [456](https://openjdk.org/jeps/456) | **Unnamed Variables & Patterns** — dùng **_** cho biến hoặc thành phần pattern không cần tham chiếu. | Final ngay trong JDK 22. | Không cần cờ đặc biệt. |
| [457](https://openjdk.org/jeps/457) | **Class-File API** — đọc, phân tích, sinh và biến đổi bytecode/class file bằng API chuẩn. | Preview ở JDK 22; final trong JDK 24 qua [JEP 484](https://openjdk.org/jeps/484), thuộc package **java.lang.classfile**. | Trên JDK 24+, không cần preview hay thêm module. |
| [458](https://openjdk.org/jeps/458) | **Launch Multi-File Source-Code Programs** — launcher có thể biên dịch các file nguồn phụ thuộc trong cùng source tree khi chạy ở source-file mode. | Tích hợp từ JDK 22 và tiếp tục được hỗ trợ. | Chạy **java Main.java**; không cần **--enable-preview**. |
| [460](https://openjdk.org/jeps/460) | **Vector API** — biểu diễn phép toán SIMD để JVM tối ưu trên phần cứng hỗ trợ vector. Java 22 là lần incubator thứ bảy. | Vẫn là incubator ở JDK 27, lần thứ mười hai qua [JEP 537](https://openjdk.org/jeps/537). | Thêm **--add-modules jdk.incubator.vector** khi biên dịch và chạy. API vẫn có thể thay đổi giữa các JDK. |
| [461](https://openjdk.org/jeps/461) | **Stream Gatherers** — mở rộng Stream bằng các phép biến đổi trung gian có trạng thái, chẳng hạn gom cửa sổ hoặc tích lũy. | Preview ở JDK 22; final trong JDK 24 qua [JEP 485](https://openjdk.org/jeps/485). | Trên JDK 24+, dùng **Stream.gather(...)** và **Gatherers** mà không cần preview. |
| [462](https://openjdk.org/jeps/462) | **Structured Concurrency** — quản lý một nhóm tác vụ đồng thời như một đơn vị, với vòng đời, hủy tác vụ và xử lý lỗi có cấu trúc. | Preview lần hai ở JDK 22; vẫn preview lần bảy ở JDK 27 qua [JEP 533](https://openjdk.org/jeps/533). | Cần **--enable-preview** khi biên dịch và chạy bằng JDK 27. API đã thay đổi qua nhiều vòng preview. |
| [463](https://openjdk.org/jeps/463) | **Implicitly Declared Classes and Instance Main Methods** — cho phép viết chương trình nhỏ mà không cần khai báo lớp tường minh hoặc **public static void main**. | Preview lần hai ở JDK 22; final trong JDK 25 qua [JEP 512](https://openjdk.org/jeps/512), tên mới là *Compact Source Files and Instance Main Methods*. | Trên JDK 25+, không cần preview. Có thể dùng **IO.println(...)** trong compact source file. |
| [464](https://openjdk.org/jeps/464) | **Scoped Values** — truyền dữ liệu chỉ đọc qua chuỗi lời gọi trong một phạm vi thực thi xác định. | Preview lần hai ở JDK 22; final trong JDK 25 qua [JEP 506](https://openjdk.org/jeps/506). | Trên JDK 25+, dùng **ScopedValue** trực tiếp, không cần preview. |

### Tính năng không đưa vào nhóm sử dụng hiện hành

**String Templates (JEP 459)** từng là preview lần hai trong JDK 22, nhưng đã bị rút trước JDK 23 sau khi nhóm phát triển đánh giá thiết kế hiện tại chưa phù hợp. Không nên xem cú pháp hoặc API preview của JEP này là một tính năng Java ổn định để đưa vào mã mới. Đây là lý do bài không đưa String Templates vào bảng thực hành.

## 3. Ví dụ nhận diện và dùng các API đã ổn định

### Biến và pattern không cần tên

Khi vòng lặp chỉ cần số lần lặp hoặc khi một thành phần của record pattern không được sử dụng, **_** thể hiện rõ ý định bỏ qua giá trị:

~~~java
int processed = 0;

for (var _ : orders) {
    processed++;
}

if (value instanceof Point(int _, int y)) {
    System.out.println("y = " + y);
}
~~~

Không dùng **_** để thay thế một biến sẽ được đọc ở câu lệnh sau. Một unnamed variable được phép khởi tạo nhưng không thể được tham chiếu.

### Stream Gatherers

Gatherers bổ sung các phép toán trung gian mà **map**, **filter** hoặc **flatMap** không mô tả trực tiếp. Ví dụ sau chia stream thành các cửa sổ có kích thước hai phần tử:

~~~java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

class GathererExample {
    public static void main(String[] args) {
        List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
                .gather(Gatherers.windowFixed(2))
                .toList();

        System.out.println(windows);
    }
}
~~~

Đây là API final từ JDK 24. Khi biên dịch bằng JDK 24 trở lên, không thêm **--enable-preview**. Nên chọn gatherer theo đúng ngữ nghĩa cần có; không thay mọi pipeline Stream bằng gatherer nếu **map**, **filter** hoặc **collect** đã đủ rõ ràng.

### Scoped Values

Scoped Values phù hợp khi một giá trị ngữ cảnh cần được truyền qua nhiều lời gọi phương thức mà không phải thêm tham số vào mọi chữ ký. Giá trị chỉ được ràng buộc trong phạm vi của tác vụ được thực thi:

~~~java
class RequestContext {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    static void handle(String requestId) {
        ScopedValue.where(REQUEST_ID, requestId)
                .run(RequestContext::process);
    }

    static void process() {
        System.out.println(REQUEST_ID.get());
    }
}
~~~

Khi **run** kết thúc, binding tự động hết hiệu lực, kể cả khi tác vụ kết thúc bằng exception. Scoped Values phù hợp với việc truyền ngữ cảnh một chiều, chỉ đọc; không nên dùng nó như một bản sao có thể thay thế mọi trường hợp của **ThreadLocal**.

### Flexible Constructor Bodies

JDK 25 cho phép kiểm tra dữ liệu trước lời gọi **super(...)** hoặc **this(...)**, miễn phần lệnh chạy trước constructor invocation không truy cập instance đang được tạo:

~~~java
class BaseAccount {
    BaseAccount(String id) {
        // Khởi tạo phần lớp cha
    }
}

class Account extends BaseAccount {
    Account(String rawId) {
        if (rawId == null || rawId.isBlank()) {
            throw new IllegalArgumentException("id không hợp lệ");
        }

        super(rawId.strip());
    }
}
~~~

Mẫu này hữu ích khi cần xác thực hoặc chuẩn hóa tham số trước khi chuyển cho constructor lớp cha. Phần lệnh trước **super(...)** không được đọc **this**, field của instance hoặc gọi instance method trên đối tượng đang khởi tạo.

### Compact Source Files và instance main method

Từ JDK 25, một chương trình nhỏ có thể bỏ phần khai báo lớp và dùng instance **main**:

~~~java
void main() {
    IO.println("Hello from modern Java");
}
~~~

Có thể lưu nội dung trên trong **Hello.java** rồi chạy bằng:

~~~shell
java Hello.java
~~~

Compact source file và khả năng launcher biên dịch nhiều file nguồn là hai tính năng riêng: JEP 512 đơn giản hóa cách viết chương trình; JEP 458 mở rộng source-file mode để xử lý các file nguồn phụ thuộc trong cùng source tree. Chúng có thể được sử dụng cùng nhau.

### Foreign Function & Memory API

FFM cung cấp **Arena**, **MemorySegment**, **Linker** và **SymbolLookup** để làm việc với bộ nhớ native hoặc gọi hàm bên ngoài JVM. Ví dụ dưới đây cấp phát một vùng nhớ native có vòng đời được quản lý bởi **Arena**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

class NativeMemoryExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 42);

            int value = segment.get(ValueLayout.JAVA_INT, 0);
            System.out.println(value);
        }
    }
}
~~~

Không phải mọi thao tác FFM đều cần bật native access. Từ JDK 24, các restricted methods liên quan đến nạp và liên kết thư viện/hàm native chịu chính sách native access thống nhất. Ví dụ cấp phát bộ nhớ ở trên không tự yêu cầu cờ này; chỉ thêm cờ khi phần khác của ứng dụng gọi restricted methods. Với ứng dụng trên classpath, lệnh khởi chạy có thể là:

~~~shell
java --enable-native-access=ALL-UNNAMED -cp out App
~~~

Với ứng dụng trên module path, chỉ bật quyền cho module thực sự cần dùng, ví dụ **--enable-native-access=com.example.app**. **ALL-UNNAMED** áp dụng rộng cho toàn bộ mã trên classpath; nên ưu tiên phạm vi module khi kiến trúc ứng dụng cho phép. Có thể kiểm tra sớm các đường gọi native chưa được cấp quyền bằng **--illegal-native-access=deny** trong môi trường kiểm thử. Các thao tác native sai có thể làm JVM crash hoặc gây hỏng bộ nhớ, vì vậy cần quản lý vòng đời **Arena** và kiểm tra biên dữ liệu cẩn thận.

### Vector API

Vector API vẫn là incubator ở JDK 27. Ví dụ sau cộng hai mảng theo từng vector và xử lý phần tử còn dư bằng vòng lặp scalar:

~~~java
import jdk.incubator.vector.IntVector;
import jdk.incubator.vector.VectorSpecies;

class VectorAdd {
    static void add(int[] left, int[] right, int[] output) {
        VectorSpecies<Integer> species = IntVector.SPECIES_PREFERRED;
        int bound = species.loopBound(left.length);
        int i = 0;

        for (; i < bound; i += species.length()) {
            IntVector a = IntVector.fromArray(species, left, i);
            IntVector b = IntVector.fromArray(species, right, i);
            a.add(b).intoArray(output, i);
        }

        for (; i < left.length; i++) {
            output[i] = left[i] + right[i];
        }
    }
}
~~~

Vector API không bảo đảm mọi phép toán đều nhanh hơn vòng lặp scalar trên mọi CPU. Hãy đo benchmark trên phần cứng mục tiêu, kiểm tra phần đuôi của mảng và duy trì đường chạy thay thế khi API incubator hoặc phần cứng không phù hợp.

### Class-File API

Từ JDK 24, API chuẩn nằm trong **java.lang.classfile**. Có thể bắt đầu bằng việc phân tích byte array của một class file:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;

class InspectClassFile {
    static ClassModel parse(byte[] classBytes) {
        ClassFile classFile = ClassFile.of();
        return classFile.parse(classBytes);
    }
}
~~~

API này phù hợp với công cụ phân tích, sinh hoặc biến đổi bytecode. Nó giúp giảm phụ thuộc vào các gói nội bộ của JDK và tự tiến hóa cùng định dạng class file. Khi xây dựng agent, framework hoặc công cụ bytecode, vẫn cần kiểm tra class file đầu vào, thuộc tính cần bảo toàn và tính tương thích của bytecode đầu ra.

## 4. Các lệnh biên dịch và chạy thường dùng

Các ví dụ dưới đây dùng JDK 27. Đổi **--release** theo phiên bản thấp nhất mà ứng dụng cần hỗ trợ.

### Chạy mã chỉ dùng tính năng đã final

Nếu triển khai trên JDK 25 LTS, biên dịch với API và cú pháp của Java 25:

~~~shell
javac --release 25 -d out src/Main.java
java -cp out Main
~~~

Nếu ứng dụng cần API chỉ có từ JDK 27, thay **25** bằng **27**. **--release** đặt phiên bản ngôn ngữ, API Java SE có thể sử dụng và định dạng class file mục tiêu; nó không tự bật preview.

### Chạy Structured Concurrency đang preview ở JDK 27

~~~shell
javac --enable-preview --release 27 -d out src/ConcurrencyDemo.java
java --enable-preview -cp out ConcurrencyDemo
~~~

Phải bật preview ở cả hai bước. Chương trình dùng preview của JDK 27 cần được chạy bằng runtime JDK 27 tương ứng. Cờ preview không biến một preview cũ của JDK 22 thành API tương thích trên JDK 27; cần cập nhật mã theo phiên bản preview hiện tại.

### Chạy Vector API đang incubate ở JDK 27

~~~shell
javac --release 27 --add-modules jdk.incubator.vector -d out src/VectorAdd.java
java --add-modules jdk.incubator.vector -cp out VectorAdd
~~~

**--add-modules** phải có ở cả compile time và runtime. Vector API là incubator module, không cần **--enable-preview**.

### Chạy chương trình dùng restricted native access

Với mã chạy trên classpath:

~~~shell
java --enable-native-access=ALL-UNNAMED -cp out Main
~~~

Với mã chạy trên module path, thay **ALL-UNNAMED** bằng tên module cần quyền. Chỉ bật native access cho thành phần thực sự gọi restricted methods.

### Chạy trực tiếp từ nhiều file nguồn

~~~shell
java src/Main.java
~~~

Launcher suy ra source root từ package của file được chạy và có thể biên dịch thêm các file **.java** cần thiết trong source tree. Cách này tiện cho ví dụ, công cụ nhỏ và thử nghiệm. Dự án có dependency ngoài, annotation processing, đóng gói, kiểm thử hoặc pipeline build phức tạp vẫn nên dùng hệ thống build như Maven hoặc Gradle.

## 5. Chọn phiên bản JDK cho dự án

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Ưu tiên nhịp cập nhật và hỗ trợ dài hạn | JDK 25 LTS, hoặc LTS mới hơn khi tổ chức nâng cấp. |
| Muốn thử tính năng mới nhất của Java | JDK 27; kiểm tra kỹ các preview/incubator trước khi đưa vào sản phẩm. |
| Duy trì tương thích với ứng dụng chạy trên Java 22 | Biên dịch bằng JDK mới với **--release 22** nếu toàn bộ API cần dùng đã có ở Java 22. |
| Dùng tính năng final hóa ở JDK 24 hoặc 25 | Đặt runtime tối thiểu tương ứng; ví dụ Gatherers/Class-File API cần JDK 24+, Scoped Values/Flexible Constructor Bodies/Compact Source Files cần JDK 25+. |
| Dùng Structured Concurrency preview | Dùng đúng JDK 27 và bật preview ở cả compile time lẫn runtime; chấp nhận việc phải cập nhật mã khi API thay đổi. |
| Dùng Vector API | Dùng incubator module tương ứng với JDK đang triển khai và đo hiệu năng trên phần cứng thực tế. |

Trước khi nâng cấp, kiểm tra phiên bản compiler và runtime thực tế trong môi trường build/deploy:

~~~shell
java -version
javac -version
~~~

Không giả định **java** và **javac** trỏ đến cùng một JDK chỉ vì cả hai đều có trong **PATH**. CI, máy phát triển và container production cần thống nhất phiên bản hoặc ghi rõ phiên bản compiler/runtime riêng.

## 6. Quy trình rà soát khi nâng cấp từ Java 22

1. **Kiểm kê preview và incubator.** Tìm các cờ **--enable-preview**, **--add-modules** và import từ **jdk.incubator.*** trong cấu hình build, test và lệnh khởi chạy.
2. **Chuyển sang API đã final.** Cập nhật mã từng dùng Class-File API, Stream Gatherers, Scoped Values, Flexible Constructor Bodies hoặc compact source files theo phiên bản final tương ứng. Không giữ cờ preview chỉ vì tính năng từng là preview trong JDK 22.
3. **Cô lập tính năng vẫn thử nghiệm.** Structured Concurrency vẫn preview ở JDK 27; Vector API vẫn incubator. Đặt chúng sau ranh giới module hoặc thành phần riêng để có thể cập nhật, thay thế và kiểm thử độc lập.
4. **Rà soát quyền native.** Với FFM/JNI, xác định module nào thực sự gọi restricted methods, bật native access có phạm vi hẹp và thử chế độ **--illegal-native-access=deny** trong kiểm thử.
5. **Chọn baseline triển khai.** Đặt **--release** theo JDK tối thiểu mà sản phẩm cam kết hỗ trợ; kiểm thử trên đúng runtime mục tiêu. **--release** không thay thế kiểm thử runtime.
6. **Đo lại hiệu năng.** Đặc biệt với Vector API và ứng dụng dùng JNI/FFM, benchmark bằng workload thật. Cải tiến GC hoặc SIMD không đồng nghĩa mọi ứng dụng đều tăng tốc như nhau.

## 7. Tài liệu tham khảo chính thức

- [Oracle Java Downloads — JDK 27 mới nhất và JDK 25 LTS](https://www.oracle.com/java/technologies/downloads/)
- [JDK 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
- [JDK 27 — Preview Features](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html)
- [JDK 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [JDK 27 — Restricted Methods và native access](https://docs.oracle.com/en/java/javase/27/core/restricted-methods.html)
- [JDK 27 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/27/gctuning/garbage-first-g1-garbage-collector.html)
- [JDK Releases — lịch phát hành và vòng đời hỗ trợ](https://ops.java/releases/)
- [JEP 423](https://openjdk.org/jeps/423), [JEP 454](https://openjdk.org/jeps/454), [JEP 456](https://openjdk.org/jeps/456), [JEP 458](https://openjdk.org/jeps/458)
- [JEP 484](https://openjdk.org/jeps/484), [JEP 485](https://openjdk.org/jeps/485), [JEP 506](https://openjdk.org/jeps/506), [JEP 512](https://openjdk.org/jeps/512), [JEP 513](https://openjdk.org/jeps/513)
- [JEP 523 — Make G1 the Default Garbage Collector in All Environments](https://openjdk.org/jeps/523), [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533), [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537), [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)

