# Dùng `javac --release` để ràng buộc cú pháp, API nền tảng và đầu ra

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt ba tầng tương thích mà trình biên dịch Java cần kiểm soát: **cú pháp/ngữ nghĩa ngôn ngữ**, **API của nền tảng Java** và **định dạng class file**.
- Sử dụng `javac --release N` để biên dịch trên một JDK mới hơn, nhưng nhắm tới một phiên bản Java cũ hơn được compiler hỗ trợ.
- Giải thích vì sao chỉ có `-source N -target N` có thể vẫn tạo class file sử dụng API không tồn tại trên runtime đích.
- Kiểm tra class-file major version bằng `javap -verbose`, nhận diện `UnsupportedClassVersionError`, `NoSuchMethodError` và các giới hạn ngoài phạm vi của `--release`.
- Cấu hình Gradle/Maven nhất quán và xác minh tính tương thích bằng chạy thử trên đúng runtime được hỗ trợ.

Bài này tập trung vào **ý nghĩa và cách dùng `--release` trong biên dịch Java**, không giải quyết toàn bộ bài toán triển khai đa nền tảng.

## 1. Tương thích Java có ít nhất ba tầng

Giả sử bạn phát triển bằng **JDK 21** nhưng ứng dụng phải chạy trên **Java 17**. Nói “code viết bằng Java 17” chưa đủ rõ: bạn còn phải hỏi source dùng cú pháp nào, gọi API nào và compiler tạo class file phiên bản nào.

| Tầng ràng buộc | Câu hỏi cần trả lời | Ví dụ rủi ro |
| --- | --- | --- |
| **Ngôn ngữ (source level)** | Có dùng tính năng cú pháp/ngữ nghĩa chỉ xuất hiện ở phiên bản mới không? | Dùng `record` nhưng yêu cầu biên dịch theo Java 11 |
| **API nền tảng (platform API)** | Những lớp, phương thức và trường của Java SE được gọi có tồn tại ở release đích không? | Dùng `List.getFirst()` (Java 21) nhưng phải chạy Java 17 |
| **Class-file target** | JVM đích có đọc được định dạng `.class` do compiler tạo không? | Class file major version 65 của Java 21 được đưa cho JVM 17 chỉ hỗ trợ mức 61 |

**`javac --release 17` ràng buộc cả ba tầng cho phần mã nguồn mà `javac` biên dịch**, dựa trên các release được phiên bản JDK đang sử dụng hỗ trợ.

Luồng cơ bản:

~~~text
JDK 21 chạy javac
         |
         | javac --release 17 -d out17 src/App.java
         v
Kiểm tra ngôn ngữ ở mức Java 17
         |
         v
Chỉ cho dùng các platform API được hỗ trợ của Java 17
         |
         v
Sinh class file target Java 17 (major version 61)
         |
         v
Có thể chạy bằng Java 17+ nếu các điều kiện runtime khác thỏa mãn
~~~

Từ “có thể” ở dòng cuối rất quan trọng: ứng dụng còn có thể lệ thuộc thư viện ngoài, native library, module configuration, file, network, OS hoặc hành vi runtime không thuộc trách nhiệm của `--release`.

### 1.1 `--release` là tùy chọn của compiler, không phải launcher

Hai lệnh này thực hiện những việc khác nhau:

~~~bash
javac --release 17 -d out17 src/App.java
java -cp out17 App
~~~

- `javac` kiểm tra source và tạo bytecode.
- `java` khởi động JVM, nạp và chạy bytecode.
- `--release 17` áp dụng **ở compile-time**. Nó không cài Java 17 trên máy, không tự thay `java` sang JVM 17 và không tạo bản JVM 17 trong thư mục output.
- Nếu lệnh `java` ở terminal đang trỏ tới Java 21, ví dụ trên vẫn sẽ được chạy bởi Java 21. Muốn xác minh khả năng chạy trên Java 17, phải thực sự thử bằng **runtime Java 17**.

Không dùng `java --release 17 App` như một cách “chọn mức Java” cho bytecode; đó không phải công dụng của tùy chọn compiler này.

## 2. `--release` khác `-source` và `-target` như thế nào?

Ba tùy chọn có trách nhiệm riêng:

| Tùy chọn của `javac` | Điều nó điều khiển | Giới hạn |
| --- | --- | --- |
| `-source 17` hoặc `--source 17` | Cấp ngôn ngữ mà source được phép dùng | **Không tự giới hạn** các API chuẩn của JDK compiler |
| `-target 17` hoặc `--target 17` | Phiên bản class file tạo ra | **Không tự giới hạn** API nền tảng được gọi |
| `--release 17` | Cấp ngôn ngữ, platform API của release 17 và class-file target 17 | Không bảo đảm mọi dependency ngoài JDK, tính năng runtime hoặc môi trường triển khai đều tương thích |

`-source` và `-target` không hoàn toàn vô ích: compiler/build tool vẫn có thể cần chúng trong các tình huống cấu hình cụ thể. Tuy nhiên, khi mục tiêu là **nhắm tới một release Java cũ hơn trên JDK mới**, `--release` thường thể hiện hợp đồng đúng hơn.

### 2.1 Vì sao chỉ đặt target class file có thể nguy hiểm?

Một class file có major version 61 được JVM 17 nhận dạng về mặt định dạng. Nhưng bên trong bytecode ấy vẫn có thể chứa lời gọi tới một method **chưa được định nghĩa trong API của Java 17** nếu bạn biên dịch nó với thư viện Java 21.

Khi đó, việc đọc class file không gặp vấn đề về major version, nhưng đến lúc liên kết hoặc thực thi lời gọi, JVM có thể gặp `NoSuchMethodError`. Lỗi này nằm ở **tương thích API/linkage**, không phải định dạng class.

`--release 17` ngăn trường hợp dùng API nền tảng Java 21 ngay khi compile bằng cách cho compiler nhìn vào API nền tảng phù hợp Java 17.

### 2.2 Cấp ngôn ngữ không đồng nghĩa cấp API

Một đoạn source có cú pháp rất cũ vẫn có thể gọi method xuất hiện muộn. Ví dụ:

~~~java
String first = java.util.List.of("Lan", "Minh").getFirst();
~~~

Lời gọi method ở đây không dùng cú pháp Java 21 đặc biệt; nhưng `List.getFirst()` được đưa vào Java 21. Trên JDK 21, `-source 17 -target 17` có thể chấp nhận biểu thức đó nếu compiler sử dụng platform API hiện tại. `--release 17` sẽ từ chối API không tồn tại ở mức đích.

Ngược lại, một API đã tồn tại trong Java 17 cũng không cho phép bạn sử dụng cú pháp chỉ có trong Java 21 khi compile với `--release 17`.

## 3. Chuẩn bị thực hành

Trong các ví dụ so sánh Java 17 và Java 21 bên dưới, hãy dùng **JDK 21 để chạy compiler**. Để chạy thử riêng trên Java 17, bạn cần thêm một runtime/JDK 17 được cài và gọi được chính xác đường dẫn của nó.

Kiểm tra compiler và launcher đang được terminal dùng:

~~~bash
javac -version
java -version
javac --help
~~~

`javac --help` liệt kê các release được **bản compiler đang cài** hỗ trợ. Không giả định một JDK bất kỳ đều có thể nhắm tới mọi phiên bản Java trong lịch sử hoặc một phiên bản tương lai.

Tạo thư mục dự án mới:

~~~text
release-demo/
└── src/
    ├── Report.java
    ├── ApiBoundary.java
    └── ApiOnly.java
~~~

Các file có thể được tạo bằng editor văn bản, lưu **UTF-8**. Mọi lệnh `javac` bên dưới được chạy từ thư mục gốc `release-demo`.

Chuẩn bị output trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out17, out21, out11, out8, out-bad | Out-Null
~~~

Hoặc trong Bash/Zsh:

~~~bash
mkdir -p out17 out21 out11 out8 out-bad
~~~

Dùng thư mục output riêng để không nhầm class file giữa các lần compile. Trong từng lệnh, `-d` chỉ nơi ghi output; tên class và package quyết định đường dẫn class bên trong.

## 4. Thực hành A: tạo class Java 17 bằng JDK 21

Tạo file **`src/Report.java`**:

~~~java
import java.util.List;
import java.util.stream.Collectors;

public record Report(String language, int count) {
    public static void main(String[] args) {
        List<String> words = List.of("JDK", "javac", "JVM");
        String keywords = words.stream()
                .map(String::toLowerCase)
                .collect(Collectors.joining(","));

        Report report = new Report("Java", words.size());
        System.out.println(report);
        System.out.println("Keywords = " + keywords);
    }
}
~~~

Đây là source **độc lập và biên dịch được trên Java 17+**. `record` là tính năng ngôn ngữ đã được chuẩn hóa từ Java 16; `List.of` có từ Java 9; `Collectors.joining` có từ Java 8.

### 4.1 Compile trên JDK 21 với release 17

~~~bash
javac --release 17 -encoding UTF-8 -d out17 src/Report.java
java -cp out17 Report
~~~

Stdout chính xác của ví dụ:

~~~text
Report[language=Java, count=3]
Keywords = jdk,javac,jvm
~~~

Chúng ta đã dùng **JDK 21 để biên dịch**, nhưng source, platform API và class-file format bị ràng buộc ở **Java 17**.

Dòng đầu thể hiện `toString()` của record. Dòng thứ hai được tạo bằng stream ghép ba từ đã chuyển sang chữ thường, theo thứ tự của danh sách.

### 4.2 Kiểm tra major version

~~~bash
javap -verbose -classpath out17 Report
~~~

Trong output, tìm:

~~~text
major version: 61
~~~

Đối với Java 17, major version 61 là phiên bản class file tương ứng. `javap -verbose` còn hiển thị nhiều metadata khác; không cần ghi nhớ thứ tự hoặc constant-pool index.

Nếu compile cùng source bằng JDK 21 mà **không đặt target thấp hơn**, class file thường mang major version **65** (Java 21):

~~~bash
javac -encoding UTF-8 -d out21 src/Report.java
javap -verbose -classpath out21 Report
~~~

Với compiler JDK 21 mặc định, bạn sẽ thấy `major version: 65`.

Không đưa `out21/Report.class` mặc định vào một JVM 17 rồi trông đợi nó chạy: JVM 17 không hỗ trợ mức class file 65 và có thể ném `UnsupportedClassVersionError`.

### 4.3 Hạ yêu cầu xuống Java 11: compiler từ chối cú pháp mới

~~~bash
javac --release 11 -encoding UTF-8 -d out11 src/Report.java
~~~

Lệnh phải thất bại vì **record** chưa phải cú pháp ngôn ngữ được hỗ trợ trong Java 11. Compiler có thể báo chẩn đoán tương đương “records are not supported in -source 11”; văn bản và số dòng diagnostic thay đổi tùy phiên bản JDK.

Điều này chứng minh một nhánh của `--release`: nó kiểm soát cấp ngôn ngữ, không chỉ tạo class file có con số version thấp hơn.

Đừng sửa warning/error bằng cách chỉ thêm `-target 11`: cú pháp record không thuộc Java 11. Nếu yêu cầu tương thích Java 11, cần thay cấu trúc ngôn ngữ bằng dạng hợp lệ cho Java 11, chẳng hạn class thông thường.

## 5. Thực hành B: ngăn dùng API Java 21 trong sản phẩm nhắm Java 17

Đây là ví dụ cho thấy **cấp ngôn ngữ hợp lệ vẫn có thể đi kèm API sai phiên bản**.

Tạo file **`src/ApiBoundary.java`**:

~~~java
import java.util.List;

public class ApiBoundary {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh");
        System.out.println(names.getFirst());
    }
}
~~~

`List.of` đã tồn tại từ Java 9. Tuy nhiên, `getFirst()` trên `java.util.List` chỉ xuất hiện cùng các sequenced collection API của **Java 21**.

### 5.1 Biên dịch mặc định bằng JDK 21

~~~bash
javac -encoding UTF-8 -d out21 src/ApiBoundary.java
java -cp out21 ApiBoundary
~~~

Với JDK 21, stdout:

~~~text
Lan
~~~

Đó là kết quả hợp lệ **trên Java 21**. Nó chưa chứng minh ứng dụng chạy được trên Java 17.

### 5.2 Dùng `--release 17`: phát hiện lỗi trước khi triển khai

~~~bash
javac --release 17 -encoding UTF-8 -d out17 src/ApiBoundary.java
~~~

Lệnh **thất bại ở compile-time** vì API `List.getFirst()` không thuộc bề mặt API của Java 17. Chẩn đoán thường bao gồm `cannot find symbol` và vị trí lời gọi `getFirst()`. Đây là lỗi đúng mong đợi: compiler đang ngăn bạn xuất bản một class dù định dạng tương thích Java 17 nhưng gọi API không có trong runtime đích.

### 5.3 Chỉ dùng `-source 17 -target 17`: bẫy tương thích

Trên compiler JDK 21, thử:

~~~bash
javac -source 17 -target 17 -encoding UTF-8 -d out-bad src/ApiBoundary.java
javap -verbose -classpath out-bad ApiBoundary
~~~

Trong môi trường JDK 21 thông thường, source này có thể **biên dịch thành công**, vì cú pháp phù hợp Java 17 và compiler vẫn nhìn thấy API Java 21. Class file được tạo có:

~~~text
major version: 61
~~~

Có thể có warning về đường dẫn system modules của target cũ; điều đó càng nhắc rằng chỉ có `-source/-target` chưa ràng buộc platform APIs.

Nếu chạy `out-bad` **bằng JVM 17 thực sự**, lời gọi `List.getFirst()` không tồn tại ở lớp `java.util.List` của Java 17 và có thể dẫn đến `NoSuchMethodError` khi gọi. Không cố định toàn bộ stack trace vì chuỗi thông báo khác theo JVM.

Điểm mấu chốt:

~~~text
JDK 21 + -source 17 -target 17
    |
    +--> Cú pháp Java 17: đạt
    +--> Class file major 61: đạt
    +--> List.getFirst() Java 21: vẫn có thể lọt vào
    |
    v
JVM 17: lỗi khi cần resolve/call method không có

JDK 21 + --release 17
    |
    +--> Cú pháp Java 17: kiểm tra
    +--> API Java 17: kiểm tra
    +--> Class file major 61: tạo nếu hợp lệ
    |
    v
Lỗi API bị phát hiện ngay lúc compile
~~~

**Đây là lợi ích cốt lõi của `--release` so với chỉ `-source/-target` khi cross-compile Java platform API.**

## 6. Thực hành C: source cũ nhưng API mới

Ví dụ trước có `List.of` (Java 9), vì vậy khó dùng để quan sát riêng API giới hạn ở Java 8. Ta dùng một source có cú pháp Java cũ nhưng gọi phương thức xuất hiện trong Java 11.

Tạo file **`src/ApiOnly.java`**:

~~~java
public class ApiOnly {
    public static void main(String[] args) {
        System.out.println("ab".repeat(3));
    }
}
~~~

Cú pháp `"ab".repeat(3)` không sử dụng record, text block hoặc pattern matching. Vấn đề là **`String.repeat(int)` được thêm ở Java 11**.

### 6.1 Nhắm Java 8

Trên JDK 21 có hỗ trợ release 8:

~~~bash
javac --release 8 -encoding UTF-8 -d out8 src/ApiOnly.java
~~~

Compiler không thể resolve `String.repeat(int)` trên API Java 8 nên báo lỗi `cannot find symbol` (method `repeat(int)`).

### 6.2 Nhắm Java 11

~~~bash
javac --release 11 -encoding UTF-8 -d out11 src/ApiOnly.java
java -cp out11 ApiOnly
~~~

Stdout:

~~~text
ababab
~~~

`javap -verbose -classpath out11 ApiOnly` sẽ hiển thị `major version: 55`, tương ứng Java 11.

Như vậy, cùng một cú pháp có thể hợp lệ ở hai source level, nhưng một **lời gọi API** chỉ hợp lệ khi platform API của release đích đã bao gồm nó.

### 6.3 Bảng ghi nhớ các mốc class file

| Java release | Major version của class file |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Bảng chỉ nói về định dạng class file; nó không cho biết class đã gọi những platform APIs nào và không thay thế việc compile với `--release`.

## 7. `--release` được compiler thực hiện ra sao?

Ở mức khái niệm, khi chạy `javac --release N`, compiler cần biết **hình dạng API nền tảng của Java release N**, chứ không đơn thuần biên dịch dựa trên các class của JDK hiện tại. Một số JDK hiện đại dùng dữ liệu biểu diễn signature lịch sử của platform APIs, chẳng hạn hệ thống thông tin đi kèm `ct.sym` của OpenJDK, để kiểm tra những symbol được phép tại release đích.

Bạn **không cần tự sửa `ct.sym` hoặc copy thư viện Java từ JDK cũ**. Cấu hình đúng là đưa `--release N` cho compiler hỗ trợ mức N. Đường đi kỹ thuật lưu chữ ký API là chi tiết của bản phân phối JDK, không nên viết script phụ thuộc vào cấu trúc file nội bộ.

### 7.1 Không phải mọi release lịch sử đều được một compiler hỗ trợ

`javac --help` hoặc tài liệu compiler hiện có sẽ nói những giá trị `--release` hợp lệ. JDK 21 chẳng hạn có thể biên dịch hướng tới nhiều release trước đó, nhưng một compiler mới trong tương lai không bắt buộc giữ hỗ trợ cho mọi release rất cũ.

Nếu compiler báo `release version ... not supported`, không có nghĩa cách viết lệnh sai; có thể **bản javac đó không hỗ trợ target được yêu cầu**. Khi ấy cần một JDK/toolchain thích hợp với release đích hoặc thay đổi chính sách hỗ trợ phiên bản của dự án.

### 7.2 `--release` không dùng để nhắm một release tương lai

JDK 17 không thể biết cú pháp, platform API và class-file target của Java 21 một cách đầy đủ. Chạy compiler JDK 17 với `--release 21` sẽ không hoạt động. Muốn nhắm Java 21 thì cần compiler hỗ trợ Java 21.

### 7.3 Java preview feature có ràng buộc riêng

Các tính năng **preview** là tính năng chưa hoàn toàn được chuẩn hóa ở thời điểm release của chúng. Cờ `--enable-preview` (khi được hỗ trợ) không phải cách dùng preview feature của một release cũ tùy ý trên compiler mới. Thông thường preview source được biên dịch và chạy theo **release hiện tại** của JDK/compiler tương ứng, với quy tắc tương thích riêng.

Đừng xem `--release 17` như quyền sử dụng mọi cú pháp từng xuất hiện dưới dạng preview trong các bản Java trước hoặc trong Java 17. Ví dụ sử dụng `record` ở trên là hợp lệ vì record đã thành tính năng chính thức từ Java 16.

### 7.4 Internal API của JDK không phải platform API công khai

Một chương trình dùng các internal JDK APIs như những package `sun.*` hoặc các package không được xuất công khai có thể không compile được dưới `--release`. Đây thường là tín hiệu code đang lệ thuộc implementation detail, thay vì API Java SE được hỗ trợ ở release đích.

`--add-exports` không phải cách tùy tiện vượt qua kiểm tra platform APIs của `--release`; phối hợp các cờ biên dịch với internal modules có các hạn chế cụ thể. Với code học tập và ứng dụng thông thường, nên ưu tiên API công khai và được hỗ trợ.

## 8. `--release` không bảo đảm những gì?

Một class file biên dịch thành công với `--release 17` **chưa phải chứng nhận ứng dụng chắc chắn chạy được ở mọi máy cài Java 17**. Có nhiều ranh giới khác cần kiểm tra.

### 8.1 Thư viện bên thứ ba

Giả sử app của bạn biên dịch với `--release 17` nhưng sử dụng một JAR được build cho Java 21. Compiler có thể không đọc được class file mới của thư viện hoặc môi trường chạy Java 17 gặp `UnsupportedClassVersionError` khi nạp class đó. `--release` chỉ điều khiển source do compiler đang biên dịch và APIs nền tảng mà compiler cho phép dùng, không viết lại bytecode của các dependency.

Một thư viện có class file major 61 vẫn có thể sử dụng các dependency/API khác không phù hợp Java 17. Bạn cần chọn **phiên bản thư viện được công bố hỗ trợ runtime đích** và kiểm tra transitive dependencies.

### 8.2 Reflection và các tên được xây dựng bằng chuỗi

Compiler chỉ kiểm tra được những lời gọi mà nó thấy theo cú pháp và kiểu thông thường. Nếu code gọi `Class.forName("some.NewClass")` hay lấy tên API từ file cấu hình, compiler có thể không phát hiện class đích chỉ có ở Java mới hơn. Kết quả phụ thuộc runtime và classpath.

Tương tự, code sinh từ runtime, plugin, bytecode instrumentation và JNI có thể đưa thêm yêu cầu mà `--release` không bao trùm. Với reflection và plugin dynamic, cần test trên runtime thực tế.

### 8.3 Hệ điều hành, kiến trúc CPU và native library

`--release 17` không cross-compile thư viện native `.dll`, `.so`, `.dylib`, không bảo đảm đường dẫn file đúng trên Windows/Linux, không bảo đảm quyền truy cập hoặc kết nối mạng. Bytecode Java có tính di động khi JVM tương thích, nhưng ứng dụng vẫn có thể phụ thuộc môi trường.

### 8.4 Tính tương thích hành vi

Ngay cả khi API tồn tại trên hai runtime, các bản cập nhật hoặc môi trường khác nhau có thể khiến hành vi phụ thuộc locale, charset, time zone, TLS/provider, khả năng xử lý file hay cấu hình hệ thống khác nhau. `--release` không thay thế integration test.

### 8.5 Dependency ở compile-time khác runtime

Nếu compiler thấy một JAR khi compile nhưng JAR đó không được đóng gói/chỉ định khi chạy, ứng dụng vẫn có thể gặp `NoClassDefFoundError`, `ClassNotFoundException` hoặc lỗi linkage khác. `--release` không tự thêm thư viện vào runtime classpath.

Đặc biệt, lỗi `UnsupportedClassVersionError` nói về class-file version; `NoSuchMethodError` nói về một method không resolve được lúc runtime. Hai lỗi này có thể cùng bắt nguồn từ vấn đề tương thích, nhưng khắc phục cần dựa trên nguyên nhân chính xác.

### 8.6 Multi-release JAR

Một JAR có thể chứa nhiều biến thể class theo cơ chế **multi-release JAR** để runtime chọn bản tương ứng. `--release` cho một tác vụ compiler chỉ tạo output theo cấp đã chỉ định; nó **không tự tạo, sắp xếp hoặc kiểm định** các biến thể multi-release.

Khi dùng multi-release JAR cần cấu hình compile, packaging, manifest và test từng release thích hợp. Đừng suy luận rằng “JAR chạy trên Java 21” đồng nghĩa mọi class được chọn khi chạy Java 17 đều tương thích.

## 9. `--release` trong Gradle và Maven

Khi project có nhiều source file và module, hãy đưa ràng buộc vào **cấu hình build** để người khác/CI không phải nhớ gõ từng lệnh.

### 9.1 Gradle — Java toolchain và release là hai trục khác nhau

Trong `build.gradle` (Groovy DSL), ví dụ dự án dùng Java plugin và muốn compiler JDK 21 tạo class nhắm Java 17:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Ở đây:

- Toolchain chọn **compiler JDK 21** (nếu Gradle có thể tìm hoặc cấp JDK phù hợp theo cấu hình).
- `options.release = 17` yêu cầu **class được biên dịch cho Java 17**, gồm cú pháp, platform API và class file.
- Điều này **không tự khiến task chạy test bằng JVM 17**. Test toolchain/launcher có thể cần cấu hình riêng nếu chính sách dự án yêu cầu test trên Java 17.
- Với multi-module build, kiểm tra cấu hình của từng module có source được phát hành cho Java 17.

Trong `build.gradle.kts` (Gradle Kotlin DSL), mô hình tương đương:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Các đoạn trên là cấu hình build cho project Java có Gradle plugin phù hợp. Phiên bản Gradle phải hỗ trợ Java toolchain/JDK được chọn; ví dụ này không nhằm chỉ định một phiên bản Gradle cụ thể.

Không nhầm `sourceCompatibility`, `targetCompatibility` với `options.release`. Trong các dự án nhắm runtime thấp hơn JDK compiler, tùy chọn release mới là thứ làm chặt ràng buộc đối với platform API.

### 9.2 Maven — cấu hình compiler release

Trong `pom.xml`, với phiên bản Maven Compiler Plugin hỗ trợ release, có thể cấu hình:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Hoặc trong cấu hình plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **các đoạn cấu hình XML** trong POM hợp lệ, không phải toàn bộ POM. Phiên bản plugin và JDK chạy compiler phải hỗ trợ việc cấu hình release tương ứng. Trong project thật, nên pin/quản lý phiên bản plugin bằng cấu hình build đã được kiểm chứng.

Đừng đoán `<source>17</source><target>17</target>` có cùng bảo đảm API như `<release>17</release>` khi build bằng JDK mới hơn. Kiểm tra cấu hình hiệu lực và compiler invocation.

### 9.3 `--release` trong CI có cần JDK đích không?

Bạn có thể biên dịch bằng JDK 21 với `--release 17`, nhưng để kiểm thử **chạy thực tế** trên Java 17, CI nên có bước chạy test/application bằng Java 17. Hướng kiểm tra:

~~~text
JDK 21 compiler + --release 17
             |
             v
     Build class/JAR
             |
             v
     Test với runtime 17
             |
             v
     (Tùy chính sách) Test thêm runtime 21
~~~

Nếu chỉ chạy test bằng JDK 21, nhiều lỗi liên quan API/behavior từ third-party code hoặc runtime reflection sẽ không xuất hiện. Một test matrix trên các runtime được hỗ trợ có giá trị hơn việc chỉ xem nhãn target class-file.

## 10. Chẩn đoán lỗi và kiểm chứng đầu ra

### 10.1 Kiểm tra compiler đang dùng release nào

Chạy:

~~~bash
javac -version
javac --help
~~~

Sau đó xem compiler arguments của build tool. Không mặc định `JAVA_HOME`, terminal, IDE, Gradle daemon và Maven toolchain đều đang dùng một JDK.

### 10.2 Kiểm tra class file

~~~bash
javap -verbose -classpath out17 Report
~~~

Tìm `major version: 61`. Với một JAR đã được build, có thể dùng `javap` với classpath trỏ tới JAR:

~~~bash
javap -verbose -classpath path/to/app.jar com.example.Main
~~~

Lệnh thứ hai là **mẫu minh họa**: thay `path/to/app.jar` và `com.example.Main` bằng artifact và class thật. Nó không phải lệnh chạy được với project `Report` ở trên nếu chưa tạo JAR tương ứng.

**Class-file version chỉ kiểm chứng tầng đầu ra**, không chứng minh mọi platform API hợp lệ. Thí nghiệm `ApiBoundary` đã cho thấy class major 61 vẫn có thể gọi API Java 21 nếu build sai cấu hình.

### 10.3 Kiểm chứng trên runtime đích

Trên máy có Java 17, hãy gọi executable `java` của bản 17, rồi chạy artifact nhắm Java 17. Ví dụ lệnh tổng quát:

~~~bash
/path/to/jdk17/bin/java -cp out17 Report
~~~

Đây là **đường dẫn mẫu**, cần thay bằng đường dẫn thực. Trên Windows đường dẫn executable là `java.exe` trong `bin` của JDK 17 và cú pháp gọi tương ứng với shell.

Trước khi kết luận, hãy xác minh phiên bản của đúng launcher đó bằng `-version`; đặc biệt quan trọng nếu máy cài nhiều JDK.

### 10.4 Các lỗi thường gặp

| Thông báo hoặc triệu chứng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| `release version 17 not supported` | Compiler quá cũ/không hỗ trợ release 17 | Chọn compiler/toolchain hỗ trợ Java 17 |
| `records are not supported in -source 11` | Source dùng tính năng ngôn ngữ mới hơn release 11 | Viết lại bằng cú pháp Java 11 hoặc nâng mức release |
| `cannot find symbol` với `List.getFirst()` khi `--release 17` | API chỉ có ở Java 21 | Dùng API tồn tại ở Java 17 (ví dụ lấy `get(0)` khi danh sách không rỗng) |
| `UnsupportedClassVersionError` trên JVM 17 | Runtime đọc class file có major lớn hơn mức hỗ trợ | Build với target tương thích và kiểm tra mọi dependency |
| `NoSuchMethodError` trên Java 17 | Binary gọi API không có trong thư viện/runtime được nạp | Dùng `--release`, căn chỉnh dependency và test runtime thực |
| Build thành công nhưng runtime không tìm class | Thiếu runtime dependency/classpath/module path | Xác minh đóng gói và classpath runtime |
| Compiler thấy API nhưng `--release` từ chối | API nằm ngoài bề mặt platform API được hỗ trợ tại release đích | Đổi API hoặc nâng mức release có chủ đích |
| `invalid flag` hoặc không nhận `--release` | Dùng bản compiler quá cũ hoặc lệnh truyền sai | Kiểm tra `javac -version`, `javac --help`, build tool arguments |
| Test trên JDK 21 đạt nhưng sản phẩm chạy JDK 17 lỗi | Chưa kiểm tra đúng runtime đích hoặc dependency không tương thích | Test trên Java 17 và rà soát artifact cuối |

### 10.5 Một sửa lỗi đúng với ví dụ `ApiBoundary`

Muốn `ApiBoundary` chạy được trên Java 17, có thể thay code dùng API Java 21 bằng cách kiểm tra danh sách không rỗng rồi gọi `get(0)`.

File **`src/ApiBoundary.java`** sau sửa:

~~~java
import java.util.List;

public class ApiBoundary {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh");
        if (!names.isEmpty()) {
            System.out.println(names.get(0));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 -d out17 src/ApiBoundary.java
java -cp out17 ApiBoundary
~~~

Stdout:

~~~text
Lan
~~~

Từ ví dụ này rút ra hai điểm: `--release` phát hiện API sai phiên bản; việc sửa cần chọn **API có cùng mục đích nhưng thật sự tồn tại ở release đích**. Việc dùng `get(0)` còn yêu cầu danh sách không rỗng, vì thế code có kiểm tra trước khi truy cập.

## 11. Chiến lược phiên bản cho dự án thật

### 11.1 Chọn runtime tối thiểu trước

Nếu nhóm tuyên bố hỗ trợ Java 17 trở lên, hãy xác định rõ **Java 17 là runtime tối thiểu**, sau đó chọn compiler JDK phù hợp và cấu hình release 17. Đừng để mặc định theo JDK của từng máy developer.

Nếu chỉ hỗ trợ Java 21, việc dùng `--release 21` trên JDK 21 vẫn có ích để cấu hình nhất quán, dù về cơ bản compiler mặc định đã nhắm tới bản đang chạy. Cần tránh vô tình đổi target chỉ vì toolchain trên máy/CI được nâng lên.

### 11.2 Dùng một cấu hình build làm nguồn kiểm soát

Đối với Gradle/Maven, đưa release vào build file. Hãy kiểm tra trong build log/compiler invocation rằng lựa chọn đó đã được áp dụng cho **các source set và module cần kiểm chứng**. Generated sources, annotation processors, mã trong module khác hoặc task tự viết có thể dùng thiết lập khác.

Trong multi-module app, một thư viện module nhắm Java 21 có thể khiến module app nhắm Java 17 không biên dịch hoặc không chạy đúng. Các module được phân phối chung phải có chính sách tương thích rõ ràng.

### 11.3 Rebuild và loại bỏ output cũ

Khi đổi từ `--release 21` sang `--release 17`, phải build lại class/JAR thật sự được phát hành. Nếu class cũ còn trong output hoặc packaging, việc xem một class mới có major 61 chưa bảo đảm artifact cuối không chứa class major 65.

Khi nghi ngờ, dùng output sạch hoặc build clean của công cụ, kiểm tra nội dung JAR, và thử load toàn bộ đường code quan trọng trên Java 17. Việc trộn nhiều mức bytecode trong một artifact chỉ phù hợp khi được thiết kế có chủ đích, chẳng hạn multi-release JAR.

### 11.4 Test behavior bên cạnh bytecode

Một chính sách xác minh tốt gồm:

1. Compile với `--release` theo runtime tối thiểu.
2. Kiểm tra artifact cuối và dependency graph.
3. Chạy unit/integration test trên runtime tối thiểu.
4. Chạy kiểm tra bổ sung trên runtime mới hơn nếu dự án hỗ trợ.
5. Theo dõi thay đổi API/behavior khi nâng JDK, framework hoặc thư viện.

Mục tiêu của `--release` là **bắt lỗi cú pháp/API nền tảng và định dạng class ngay khi compile**. Các kiểm tra còn lại xử lý những giới hạn mà compiler không thể bảo đảm một mình.

## 12. Bài tập thực hành có đáp án

### Bài 1 — Phân biệt từng tầng tương thích

Bạn dùng JDK 21, nhưng ứng dụng phải chạy Java 17. Đánh giá các cấu hình:

| Cấu hình | Cú pháp Java 17 | API nền tảng Java 17 | Class-file target Java 17 |
| --- | --- | --- | --- |
| `javac --release 17` | Có | Có | Có |
| `javac -source 17 -target 17` trên JDK 21 | Có | Không được bảo đảm | Có |
| `javac` mặc định của JDK 21 | Java 21 | Java 21 | Java 21 |

**Đáp án:** cấu hình đầu phù hợp nhất khi dùng JDK 21 để nhắm Java 17, vì có thêm ràng buộc API. Cấu hình thứ hai dễ lọt lời gọi chỉ có ở platform API mới, còn cấu hình thứ ba mặc định nhắm Java 21.

### Bài 2 — Dự đoán kết quả `Report.java`

Trên JDK 21, thử:

~~~bash
javac --release 17 -d out17 src/Report.java
javac --release 11 -d out11 src/Report.java
~~~

**Đáp án:** lệnh đầu thành công vì record được hỗ trợ ở Java 17; lệnh hai thất bại do record không được hỗ trợ ở source level 11. Output mặc định của ví dụ thứ nhất là hai dòng `Report[language=Java, count=3]` và `Keywords = jdk,javac,jvm`.

### Bài 3 — Tại sao major version 61 chưa đủ?

Compile `ApiBoundary.java` với `-source 17 -target 17` trên JDK 21, rồi phân tích khả năng chạy trên Java 17.

**Đáp án:** class major 61 có định dạng được Java 17 hiểu, nhưng lời gọi `List.getFirst()` không có trên API Java 17. Khi method được thực thi, runtime có thể báo `NoSuchMethodError`. `--release 17` ngăn lỗi ngay khi compile.

### Bài 4 — Sửa API để phù hợp release

Thay `names.getFirst()` bằng đoạn xử lý `names.get(0)` khi danh sách không rỗng, rồi compile:

~~~bash
javac --release 17 -d out17 src/ApiBoundary.java
java -cp out17 ApiBoundary
~~~

**Đáp án:** sau khi sửa source theo mục 10.5, compiler chấp nhận và stdout là `Lan`. Việc kiểm tra danh sách không rỗng tránh lỗi truy cập index trên danh sách rỗng.

### Bài 5 — API Java 11 trên target Java 8

Với `ApiOnly.java`, vì sao `--release 8` từ chối `String.repeat` còn `--release 11` chấp nhận?

**Đáp án:** `String.repeat(int)` xuất hiện từ Java 11. Cú pháp của lời gọi là cú pháp thông thường, nhưng **platform API** khác giữa release 8 và 11.

### Bài 6 — Đọc class file không nhầm kết luận

`javap -verbose` cho `major version: 61`. Bạn được kết luận những gì?

**Đáp án:** class file có định dạng target Java 17. Bạn chưa được kết luận mọi thư viện runtime đều tương thích hoặc code không dùng API mới, vì một class major 61 vẫn có thể được compile sai bằng `-source/-target` và gọi API của JDK 21.

### Bài 7 — Thiết lập Gradle/Maven

Trong dự án có toolchain JDK 21 và runtime tối thiểu Java 17, cần khai báo gì?

**Đáp án:** Gradle dùng `options.release = 17` hoặc `options.release.set(17)` tùy DSL; Maven dùng `maven.compiler.release=17` hoặc `<release>17</release>` của compiler plugin hỗ trợ. Sau đó build lại, xem class file và test trên runtime Java 17.

## 13. Checklist trước khi phát hành

- [ ] Đã xác định rõ **runtime Java tối thiểu** mà sản phẩm hỗ trợ.
- [ ] Compiler được chọn hỗ trợ giá trị `--release` cần dùng.
- [ ] Cấu hình compile ràng buộc **ngôn ngữ + platform API + class file**, ưu tiên `--release` khi phù hợp.
- [ ] Đã kiểm tra không sử dụng preview/internal API ngoài chính sách dự án.
- [ ] Đã build lại các class/JAR và tránh trộn artifact cũ.
- [ ] Đã kiểm tra major class-file version của những artifact quan trọng.
- [ ] Dependency và thư viện bên ngoài tương thích với runtime đích.
- [ ] Runtime classpath/module path chứa đúng artifact khi chạy.
- [ ] Đã chạy thử trên **đúng JVM tối thiểu**, không chỉ JDK mới hơn ở máy developer.
- [ ] Các môi trường OS, native libraries, quyền truy cập và cấu hình runtime cần thiết đều được xác minh.

## Ghi nhớ

**`javac --release N` đặt một hợp đồng compile-time về cú pháp Java, API nền tảng và class-file target của release N.** Đây là khác biệt quan trọng so với việc chỉ đặt `-source N -target N`, vì code có thể mang định dạng class cũ nhưng gọi API Java mới. Để bảo đảm ứng dụng triển khai được, kết hợp `--release` với dependency phù hợp, build sạch và kiểm thử trực tiếp trên runtime tối thiểu mà bạn công bố hỗ trợ.