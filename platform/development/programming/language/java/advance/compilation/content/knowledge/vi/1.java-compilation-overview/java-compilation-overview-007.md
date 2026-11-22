# Kiến thức cần có và cách thực hành với một dự án nhỏ — Java Compilation

## 1. Mục tiêu của bài học

Sau bài này, bạn có thể tự giải thích Java biến mã nguồn thành chương trình chạy được như thế nào, sử dụng bộ công cụ JDK để biên dịch và chạy một dự án nhiều tệp, nhận biết lỗi xuất hiện lúc biên dịch hay lúc chạy, đồng thời quan sát sản phẩm đầu ra là bytecode. Bài thực hành không cần IDE, Maven, Gradle hoặc thư viện ngoài; vì vậy mỗi bước của trình biên dịch đều hiện rõ.

**Phạm vi:** cơ sở của biên dịch Java với JDK 17 trở lên. Các công cụ build và cơ chế tối ưu chuyên sâu chỉ được nhắc đến tại điểm chúng có liên quan.

## 2. Bức tranh tổng thể: từ .java tới chương trình chạy

Một chương trình Java thông thường đi qua các bước:

~~~text
App.java + ScoreUtils.java
        |
        v
javac: đọc mã nguồn, phân tích cú pháp, tra tên, kiểm tra kiểu,
       xử lý annotation nếu có, tạo mã bytecode
        |
        v
App.class + ScoreUtils.class
        |
        v
java: khởi động JVM, nạp/liên kết/khởi tạo lớp khi cần
        |
        v
thực thi bytecode (trình thông dịch và/hoặc mã máy do JIT biên dịch)
        |
        v
kết quả trên console
~~~

- **Mã nguồn (.java)** là văn bản được viết theo cú pháp ngôn ngữ Java.
- **javac** là trình biên dịch Java của JDK. Nó kiểm tra chương trình và thường sinh một tệp .class cho mỗi lớp, record, interface hoặc kiểu được tạo ra. Một tệp nguồn cũng có thể tạo nhiều .class do lớp lồng nhau.
- **Bytecode (.class)** là định dạng lệnh và metadata dành cho JVM, không phải mã máy của Windows/Linux/macOS. Định dạng này giúp cùng một artifact chạy trên các JVM tương thích.
- **JVM** thực hiện nạp lớp, kiểm tra bytecode và liên kết khi cần; lúc chạy JVM có thể thông dịch hoặc JIT-compile những đoạn nóng thành mã máy. JIT diễn ra ở thời gian chạy, khác với bước javac trước đó.
- **JDK** bao gồm javac, java, javap và các công cụ phát triển. Chỉ có một môi trường chạy Java không bảo đảm bạn có lệnh javac.

Điểm phân biệt cốt lõi: **javac có thể thành công mà chương trình vẫn lỗi lúc chạy**, chẳng hạn thiếu một lớp trong classpath hoặc dùng bộ .class không tương thích. Ngược lại, một lỗi kiểu trong mã nguồn thường bị javac chặn trước khi chương trình chạy.

### Những gì javac thực sự kiểm tra

| Giai đoạn khái quát | Câu hỏi cần trả lời | Ví dụ lỗi |
| --- | --- | --- |
| Phân tích token/cú pháp | Câu lệnh, dấu ngoặc, khai báo có hợp lệ? | Thiếu dấu ; hoặc dấu } |
| Phân giải tên/ký hiệu | Lớp, biến, phương thức được nhắc tới có tồn tại và truy cập được? | cannot find symbol |
| Kiểm tra kiểu và ràng buộc | Kiểu tham số, kiểu trả về, generic, phạm vi truy cập có tương thích? | incompatible types |
| Xử lý annotation (nếu có processor) | Có nguồn mới được tạo hay có kiểm tra bổ sung? | Lỗi processor hoặc mã được sinh |
| Tạo bytecode | Ghi định nghĩa lớp, phương thức và lệnh vào .class | Đầu ra không được tạo nếu biên dịch lỗi |

Đây là mô hình học tập, không phải cam kết rằng javac luôn chạy tuần tự đúng năm pha độc lập. Chi tiết nội bộ của compiler có thể thay đổi theo phiên bản JDK.

## 3. Kiến thức nền tảng cần có trước khi thực hành

**Java cơ bản:** biết khai báo lớp, phương thức static, biến cục bộ, vòng lặp for-each, List, lời gọi phương thức và kiểu int/double. Khi đọc mã, hãy theo dõi kiểu tham số và kiểu trả về vì đây chính là hợp đồng mà javac kiểm tra.

**Tệp, thư mục và package:** với khai báo package demo.compilation, đặt nguồn ở thư mục src/demo/compilation là quy ước dễ quản lý. Tên tệp của một public top-level class phải trùng tên lớp: public class App thuộc tệp App.java. Tên package có phân biệt hoa/thường.

**Terminal:** biết chuyển tới thư mục gốc dự án, gõ lệnh, đọc exit code và thông báo lỗi. Lệnh javac nhận đường dẫn tệp nguồn; lệnh java nhận **tên lớp đầy đủ**, không nhận đường dẫn tệp .class khi chạy theo cách classpath thông thường.

**Classpath:** danh sách vị trí JVM hoặc javac tìm các lớp và thư viện. Với thư mục đầu ra out, classpath phải trỏ vào **out**, tức thư mục gốc của cây package, thay vì trỏ thẳng tới out/demo/compilation. Classpath lúc biên dịch và lúc chạy là hai cấu hình khác nhau, cần được cung cấp đúng ở từng lệnh.

**Phiên bản:** JDK dùng để biên dịch, mức ngôn ngữ/API đích và phiên bản JVM dùng để chạy có thể khác nhau. Với ví dụ này, dùng JDK 17+ và chỉ yêu cầu tính năng/API Java 17.

### Kiểm tra môi trường

Chạy các lệnh sau trong terminal:

~~~sh
java -version
javac -version
javap -version
~~~

Kỳ vọng: cả ba lệnh hoạt động và phiên bản JDK ít nhất là 17. Chuỗi version đầy đủ phụ thuộc bản phân phối/cập nhật của máy, nên không cần khớp một chuỗi cố định. Nếu javac không được tìm thấy, hãy kiểm tra JDK đã cài và cấu hình PATH/JAVA_HOME. Trên máy có nhiều JDK, bảo đảm java và javac đang trỏ đúng bộ công cụ dự định dùng.

## 4. Dự án nhỏ: tính tổng và trung bình điểm

Ta tạo dự án tên **compilation-lab** với hai lớp. App điều phối chương trình, ScoreUtils chứa logic tính tổng. Tách lớp giúp nhìn thấy phụ thuộc biên dịch giữa các tệp và vai trò của classpath.

~~~text
compilation-lab/
└── src/
    └── demo/
        └── compilation/
            ├── App.java
            └── ScoreUtils.java
~~~

Thư mục out sẽ do javac tạo khi chạy lệnh có tùy chọn -d.

### Tệp 1: src/demo/compilation/ScoreUtils.java

~~~java
package demo.compilation;

import java.util.List;

public final class ScoreUtils {
    private ScoreUtils() {
        // Lớp tiện ích không cần tạo instance.
    }

    public static int total(List<Integer> scores) {
        int sum = 0;
        for (int score : scores) {
            sum += score;
        }
        return sum;
    }
}
~~~

Hợp đồng của phương thức total là: nhận List<Integer>, trả về int. Vòng lặp tự unbox mỗi Integer thành int. Ví dụ dùng dữ liệu nhỏ; nếu tổng có thể vượt phạm vi int, ứng dụng thực tế cần chọn kiểu và chính sách xử lý tràn số thích hợp.

### Tệp 2: src/demo/compilation/App.java

~~~java
package demo.compilation;

import java.util.List;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        List<Integer> scores = List.of(8, 9, 10);
        int total = ScoreUtils.total(scores);

        System.out.println("Count: " + scores.size());
        System.out.println("Total: " + total);
        System.out.println("Average: " + (total / (double) scores.size()));
    }
}
~~~

**Vì sao code có thể được biên dịch?** Java tìm thấy List trong thư viện chuẩn, cùng với ScoreUtils trong package demo.compilation. Lời gọi ScoreUtils.total(scores) nhận List<Integer> và trả int; phép ép (double) khiến phép chia ra số thực. Phương thức main có chữ ký phù hợp để Java launcher gọi.

**Giả định:** danh sách có ít nhất một phần tử để phép tính trung bình có ý nghĩa. Bài này dùng danh sách cố định ba điểm, nên không phát sinh phép chia cho 0.

## 5. Biên dịch lần đầu và chạy chương trình

Mở terminal tại thư mục compilation-lab (thư mục chứa src).

Với Bash trên macOS/Linux, có thể tạo thư mục đầu ra bằng:

~~~sh
mkdir -p out
~~~

Với PowerShell trên Windows, lệnh tương ứng là:

~~~powershell
New-Item -ItemType Directory -Path out -Force
~~~

Biên dịch **cả hai tệp nguồn**; cách liệt kê rõ hai tệp chạy được trên Bash và PowerShell:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/compilation/ScoreUtils.java src/demo/compilation/App.java
~~~

Khi thành công, javac thường không in gì ra terminal và tạo:

~~~text
out/
└── demo/
    └── compilation/
        ├── App.class
        └── ScoreUtils.class
~~~

Chạy bằng classpath trỏ tới thư mục out và tên lớp đầy đủ:

~~~sh
java -cp out demo.compilation.App
~~~

**Kết quả chuẩn** của đúng hai tệp nguồn ở trên:

~~~text
Count: 3
Total: 27
Average: 9.0
~~~

Cách đọc các tùy chọn:

| Lệnh hoặc tùy chọn | Tác dụng |
| --- | --- |
| javac | Biên dịch mã nguồn Java thành bytecode .class |
| -encoding UTF-8 | Giải mã tệp nguồn bằng UTF-8, tránh phụ thuộc encoding mặc định máy |
| --release 17 | Biên dịch theo mức ngôn ngữ, bytecode và API công khai của Java 17 |
| -d out | Đặt gốc thư mục chứa .class được sinh vào out, giữ cấu trúc package |
| java -cp out | Đưa out vào application classpath lúc chạy |
| demo.compilation.App | Tên lớp chứa main, gồm package và tên class |

Lệnh java -cp out demo.compilation.App **không** yêu cầu tệp App.java còn tồn tại, vì JVM chạy bytecode từ .class. Tuy nhiên, nếu sửa .java mà không chạy lại javac, kết quả chạy vẫn lấy từ .class cũ.

## 6. Quan sát bytecode đã sinh

Dùng javap, công cụ đọc thông tin từ tệp .class:

~~~sh
javap -classpath out -p demo.compilation.ScoreUtils
javap -classpath out -c demo.compilation.App
javap -classpath out -verbose demo.compilation.App
~~~

Ở lệnh đầu, bạn sẽ nhìn thấy khai báo phương thức có ý nghĩa tương đương public static int total(java.util.List<java.lang.Integer>). Tùy chọn -p còn hiển thị thành viên private. Ở lệnh thứ hai, bạn thấy các instruction bytecode như invokestatic, invokevirtual, getstatic hoặc invokedynamic (tùy JDK và dạng biểu thức); đây **không** phải cú pháp nguồn Java.

Với lệnh -verbose, tìm dòng **major version: 61**. Khi biên dịch bằng --release 17, major version 61 tương ứng class-file format của Java 17. Đây là một dấu hiệu kiểm chứng mức bytecode đích; nó không tự chứng minh thư viện bên ngoài hay môi trường chạy đã tương thích.

Hãy tìm lời gọi tới ScoreUtils.total trong danh sách instruction/constant pool: class App ghi một tham chiếu tới phương thức ở lớp khác. Vì vậy runtime vẫn phải có đúng phiên bản tương thích của ScoreUtils.class trên classpath.

## 7. Biên dịch riêng từng lớp: classpath lúc compile

Khi biên dịch các lớp theo từng lượt, trình biên dịch của App cần nhìn thấy ScoreUtils đã biên dịch.

Bắt đầu với ScoreUtils:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/demo/compilation/ScoreUtils.java
~~~

Sau đó biên dịch riêng App và cung cấp classpath:

~~~sh
javac -encoding UTF-8 --release 17 -cp out -d out src/demo/compilation/App.java
java -cp out demo.compilation.App
~~~

Kết quả vẫn là ba dòng Count/Total/Average như ở phần 5. Tham số -cp out trong lệnh javac cho phép compiler tra cứu ScoreUtils.class. Trong lệnh java, -cp out cho JVM tra cứu cả App.class và ScoreUtils.class.

Nếu App cần một JAR ngoài, phải cấu hình dependency để compiler nhìn thấy API của thư viện khi biên dịch và để JVM tìm thấy phiên bản tương thích khi chạy. Maven/Gradle tự quản lý nhiều bước đó, nhưng bản chất vẫn là biên dịch với dependency và chạy với runtime classpath/module path phù hợp.

**Đừng nhầm:** -d chỉ định **nơi ghi** .class; -cp chỉ định **nơi tìm** các lớp đã có. Hai tùy chọn không thay thế nhau.

## 8. Thí nghiệm có chủ đích: thấy rõ lỗi ở giai đoạn nào

Các thí nghiệm sau làm **lần lượt**, từ bản mã chạy tốt. Trước mỗi thí nghiệm mới, khôi phục hai tệp nguồn như phần 4 nếu đã sửa chúng. Thực hiện trong bản sao dự án hoặc dưới hệ thống quản lý phiên bản để dễ quay lại.

### Thí nghiệm A — Sai tên phương thức: lỗi compile-time

Trong App.java, thay đúng một dòng:

~~~java
int total = ScoreUtils.totals(scores);
~~~

Giữ nguyên tên phương thức trong ScoreUtils là total, rồi biên dịch lại cả hai nguồn bằng lệnh phần 5. javac sẽ báo lỗi dạng **cannot find symbol** cho lời gọi totals, vì không có phương thức tên đó. Chi tiết dòng/cột của diagnostic có thể khác theo JDK.

**Sửa:** đổi totals về total, biên dịch lại và chạy. Lỗi này được phát hiện trước khi thực thi main.

### Thí nghiệm B — Sai kiểu tham số: lỗi compile-time

Giả sử App khai báo:

~~~java
List<String> scores = List.of("8", "9", "10");
int total = ScoreUtils.total(scores);
~~~

ScoreUtils.total yêu cầu List<Integer>. List<String> không tương thích với List<Integer> vì generic Java bất biến theo tham số kiểu. javac phát hiện sự khác biệt kiểu ở lời gọi, dù các chuỗi trông giống chữ số. Để sửa, dùng dữ liệu Integer hoặc chuyển đổi có kiểm soát sang danh sách số nguyên trước khi gọi.

### Thí nghiệm C — Thiếu classpath hoặc sai gốc package

Giả sử chỉ có App.java đang được biên dịch riêng, còn ScoreUtils.class nằm trong out. Nếu không chỉ ra -cp out và javac cũng không tìm được nguồn ScoreUtils qua source path, trình biên dịch không phân giải được lớp phụ thuộc.

Cấu hình đúng:

~~~sh
javac -encoding UTF-8 --release 17 -cp out -d out src/demo/compilation/App.java
~~~

Lúc chạy, nếu đặt classpath sai gốc, JVM có thể báo **ClassNotFoundException** trong một số cơ chế nạp lớp hoặc **NoClassDefFoundError** khi một lớp phụ thuộc không được tìm thấy lúc liên kết/thực thi. Java launcher cũng có thể báo **Could not find or load main class** nếu chính lớp main không được tìm thấy. Các lỗi này thuộc runtime/class loading, không đồng nghĩa với lỗi cú pháp nguồn.

### Thí nghiệm D — .class cũ và thay đổi chữ ký phương thức

Đây là minh họa nâng cao nhưng rất thực tế về khác biệt giữa kiểm tra nguồn và liên kết ở runtime.

1. Quay lại bản gốc chạy tốt, biên dịch cả hai tệp, chạy để xác nhận.
2. Trong ScoreUtils.java, chỉ đổi kiểu trả về từ **int** thành **long** ở khai báo phương thức total; giữ thân phương thức trả về sum (Java tự chuyển int sang long).
3. Chỉ biên dịch lại ScoreUtils.java, **không biên dịch lại App.java**:

~~~sh
javac -encoding UTF-8 --release 17 -cp out -d out src/demo/compilation/ScoreUtils.java
java -cp out demo.compilation.App
~~~

Bạn sẽ gặp lỗi runtime dạng **NoSuchMethodError** đối với phương thức total có descriptor cũ trả int. App.class cũ vẫn tham chiếu chữ ký đã biên dịch trước đó. Trong bytecode, kiểu trả về là một phần của method descriptor; chữ ký nhị phân mới không khớp.

Nếu biên dịch lại App.java bằng mã cũ, javac lại phát hiện vấn đề ở compile-time: không thể tự động gán giá trị long vào biến int total. Để sửa nhất quán, thay App.java thành:

~~~java
long total = ScoreUtils.total(scores);
~~~

Rồi biên dịch lại **cả hai tệp** và chạy. Kết quả văn bản vẫn là Count: 3, Total: 27, Average: 9.0. Bài học: thay API của thư viện có thể làm hỏng binary client chưa được rebuild ngay cả khi cả hai bên từng biên dịch riêng thành công.

## 9. Biên dịch Java khác gì thực thi Java?

| Tiêu chí | Thời gian biên dịch | Thời gian chạy |
| --- | --- | --- |
| Công cụ điển hình | javac | java launcher + JVM |
| Đầu vào chính | .java và dependency cần thiết | .class/JAR và dependency runtime |
| Kết quả | .class hoặc thông báo lỗi | Chạy chương trình hoặc exception/error |
| Lỗi hay gặp | Cú pháp, kiểu, tên, visibility | Thiếu lớp/JAR, thay đổi nhị phân, lỗi dữ liệu, exception |
| Cấu hình tìm lớp | classpath/module path của javac | classpath/module path của JVM |
| Công nghệ tối ưu | Phân tích và sinh bytecode bởi compiler | Interpreter/JIT của JVM, tùy runtime |

**JIT không thay thế javac:** JIT làm việc trên mã trung gian trong lúc chạy (theo cơ chế JVM). Bytecode có thể được thông dịch trước khi hoặc thay vì được JIT compile.

**Không phải mọi .java cần bước javac thủ công:** từ Java 11, java có chế độ chạy một tệp nguồn (source-file mode). Launcher vẫn thực hiện công việc biên dịch liên quan phía sau. Chế độ đó tiện cho ví dụ đơn giản nhưng không thay thế việc nắm rõ biên dịch dự án nhiều lớp và classpath.

**Không phải mỗi lần sửa đều đủ để chạy lại:** cần bảo đảm các .class được cập nhật. Một số IDE/build tool làm tự động, khiến người học dễ bỏ qua cơ chế nền.

## 10. Phiên bản JDK, --release và tính tương thích

Giả sử bạn dùng JDK 21 để phát triển nhưng muốn artifact chạy trên Java 17. Lệnh của bài thực hành dùng --release 17 để yêu cầu javac kiểm tra theo API công khai và cú pháp Java 17, đồng thời sinh class-file version phù hợp. Nếu bạn vô tình gọi một API chỉ có ở Java mới hơn, --release 17 giúp compiler từ chối.

Phân biệt các khái niệm:

- **Phiên bản JDK đang chạy javac:** phiên bản compiler/toolchain thực tế.
- **Mức nguồn/bytecode đích:** mức ngôn ngữ và class-file format được sinh; --release kết hợp các ràng buộc liên quan.
- **Phiên bản runtime:** JVM thực sự nạp và chạy .class. JVM cũ hơn mức class-file yêu cầu có thể ném UnsupportedClassVersionError.
- **Tương thích dependency:** thư viện bên ngoài cũng phải có bytecode/API tương thích. --release cho mã nguồn của bạn không tự làm cho một JAR biên dịch bằng Java mới hơn chạy được trên Java cũ.

Chỉ dùng -source và -target không phải luôn đủ để ngăn mã nguồn tham chiếu API của platform mới khi biên dịch bằng JDK mới; với mục tiêu Java 17, --release 17 thường là lựa chọn phù hợp hơn. Không dùng đường dẫn tới JDK 17 và --release 17 như hai khái niệm đồng nghĩa: một bên chọn công cụ, một bên giới hạn mục tiêu biên dịch.

## 11. Lỗi thường gặp và cách khoanh vùng nhanh

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra trước |
| --- | --- | --- |
| javac: command not found / is not recognized | Thiếu JDK hoặc PATH sai | javac -version; đường dẫn JDK |
| error: cannot find symbol | Sai tên, thiếu import/dependency, lớp chưa được nhìn thấy | Tên phương thức/lớp, package, compile classpath |
| incompatible types | Lời gọi, gán biến hoặc generic không hợp kiểu | Kiểu thực tế và kiểu khai báo trong method signature |
| class ... is public, should be declared in a file named ... | Public top-level class không trùng tên tệp | Tên tệp và tên lớp |
| package ... does not exist | Thiếu JAR/lớp hoặc package sai | classpath/module path lúc biên dịch |
| Could not find or load main class | Sai tên lớp đầy đủ hoặc classpath chạy | java -cp out demo.compilation.App |
| NoClassDefFoundError | JVM thiếu lớp phụ thuộc lúc nạp/liên kết | Runtime classpath và artifact đã đóng gói |
| NoSuchMethodError | Caller và dependency không tương thích nhị phân | Rebuild đồng bộ, kiểm tra phiên bản JAR |
| UnsupportedClassVersionError | .class mới hơn JVM đang chạy | java -version và mức --release |
| Chạy vẫn ra kết quả cũ sau khi sửa .java | Tệp .class chưa được biên dịch lại hoặc chạy nhầm artifact | Xóa đầu ra cũ trong dự án thực hành rồi build lại |

Đọc **dòng chẩn đoán đầu tiên có ý nghĩa**, vị trí tệp và dòng nguồn; sửa nguyên nhân trước khi xử lý hàng loạt lỗi kéo theo. Với lỗi runtime, đọc loại exception/error, stack trace và cấu hình chạy. Tránh sửa classpath một cách ngẫu nhiên hoặc trộn nhiều phiên bản cùng một thư viện.

### Cẩn thận với output cũ

Nếu compile thất bại nhưng out vẫn có App.class từ lượt trước, lệnh java có thể tiếp tục chạy bản cũ và tạo cảm giác mã sai vẫn “hoạt động”. Trong bài thực hành, hãy bảo đảm build thành công từ nguồn hiện hành trước khi kết luận. Khi kiểm thử một bản dựng sạch, xóa riêng thư mục out của **dự án mẫu** rồi chạy lại javac; đừng xóa thư mục tùy ý của dự án thật.

## 12. Bài tập tự kiểm tra

Thực hành lần lượt và tự dự đoán kết quả trước khi dùng terminal:

1. Biên dịch hai nguồn và chạy chương trình. Ghi nhận ba dòng stdout đúng như phần 5. Mở out để xác nhận đường dẫn hai .class.
2. Dùng javap đọc method total và tìm lời gọi tới nó từ App. Giải thích vì sao JVM vẫn cần ScoreUtils.class mặc dù App.class đã được tạo.
3. Thay bộ điểm thành List.of(6, 7, 8). Dự đoán rồi xác nhận kết quả: Count: 3, Total: 21, Average: 7.0. Nếu quên compile lại, quan sát sự khác biệt.
4. Đổi totals thành tên phương thức không tồn tại. Đọc lỗi javac và sửa. Chỉ dùng IDE nếu bạn đã hiểu lệnh terminal tương ứng.
5. Biên dịch từng tệp theo phần 7, sau đó giải thích vai trò khác nhau của -cp và -d.
6. Nếu đang dùng JDK mới hơn 17, giữ --release 17, thử gọi một API chỉ có từ phiên bản Java mới hơn rồi quan sát compiler từ chối. Không cần ép dùng API cụ thể nếu JDK máy không phù hợp.

**Tiêu chí hoàn thành:** bạn tự chạy được dự án từ hai tệp .java, biết vị trí .class và package tương ứng, giải thích được compiler kiểm tra những gì, phân biệt lỗi compile-time với runtime, biết dùng --release/-encoding/-d/-cp, và hiểu vì sao rebuild đồng bộ là cần thiết sau khi thay đổi API.

## 13. Tư duy áp dụng vào dự án thực tế

Trong ứng dụng lớn, Maven/Gradle thường quản lý việc tìm source, tải dependency, gọi compiler, lưu bytecode, chạy test và đóng gói JAR. Khi gặp lỗi build, hãy quy về các câu hỏi nền tảng:

- **Nguồn nào đang được biên dịch?** Đúng tệp/module/source set hay một bản khác?
- **Compiler được chọn là JDK nào?** Có đúng mức Java và --release/sourceCompatibility yêu cầu?
- **Khi biên dịch thấy dependency nào?** Có thiếu classpath, import hoặc sai version?
- **Artifact chạy thật sự là artifact nào?** Đường dẫn .class/JAR và entry point có chính xác?
- **Runtime thấy dependency nào?** Có thiếu JAR hoặc mismatch với API lúc biên dịch?
- **Có bytecode cũ không?** Rebuild sạch phạm vi cần thiết để loại stale output.

Nắm rõ chu trình **source → javac → bytecode → JVM** giúp bạn đọc lỗi đúng tầng, xử lý có căn cứ và không lệ thuộc vào một IDE hay build tool cụ thể.
