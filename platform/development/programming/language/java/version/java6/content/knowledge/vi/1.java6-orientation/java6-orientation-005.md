# Thực hành trên JDK được hỗ trợ với các API có nguồn gốc từ Java 6

Một API xuất hiện từ Java 6 có thể vẫn là công cụ hữu ích trong JDK hiện đại. Ta học **vấn đề API giải quyết và hợp đồng hiện hành của nó**, rồi thực hành trên một JDK đang được nhà cung cấp duy trì.

Bài này dùng ba tình huống nhỏ: tra mốc theo thứ tự bằng `NavigableMap`, xử lý hai đầu bằng `ArrayDeque`, và gọi trình biên dịch qua `JavaCompiler`. Chúng giúp nối kiến thức lịch sử của module với cách viết và chạy Java hiện nay.

## 1. Tách ba ý nghĩa của “phiên bản Java”

| Câu hỏi | Ý nghĩa |
| --- | --- |
| API có nguồn gốc từ phiên bản nào? | Mốc API được giới thiệu, chẳng hạn `Since: 1.6` |
| Mã được biên dịch với mức nền nào? | Mức cú pháp, API và class file mà cấu hình biên dịch cho phép |
| JVM nào thực sự chạy chương trình? | JDK/runtime đang được terminal hoặc IDE sử dụng |

Ba câu hỏi có thể có ba đáp án khác nhau. Trong bài:

- API trọng tâm có nguồn gốc từ Java 6.
- Lệnh biên dịch dùng `--release 17`.
- Ví dụ được chạy kiểm chứng trên Microsoft OpenJDK 21.0.9.

Như vậy, kết quả là thực hành API còn áp dụng trên JDK hiện đại; nó không tuyên bố chương trình đã được kiểm thử trên Java 6.

Với môi trường học mới, dùng bản cập nhật được nhà cung cấp hỗ trợ của một dòng JDK phù hợp, chẳng hạn 21 hoặc 25. Trạng thái hỗ trợ và thời hạn cập nhật phụ thuộc nhà cung cấp; “LTS” không tự bảo đảm một bản vá cũ đang cài là bản nên tiếp tục dùng. Ví dụ, [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) xác định 21 và 25 là các dòng LTS trong chính sách của Oracle.

## 2. Chọn phần kiến thức còn dùng được

| API | Nguồn gốc | Bài toán hiện nay |
| --- | --- | --- |
| `NavigableMap` | Java 6 | Tìm khóa gần nhất theo quan hệ nhỏ hơn/lớn hơn |
| `ArrayDeque` | Java 6 | Hàng đợi hai đầu, xử lý FIFO hoặc LIFO trong một luồng |
| `ToolProvider` và Java Compiler API | Java 6 | Công cụ Java cần gọi trình biên dịch qua API |
| `ServiceLoader` | Java 6 | Tìm triển khai dịch vụ được phân phối theo quy ước |
| `Console` | Java 6 | Tương tác với thiết bị console nếu môi trường có cung cấp |

Ba hàng đầu được thực hành đầy đủ bên dưới. Hai hàng cuối là hướng mở rộng; mỗi API có hợp đồng môi trường riêng. Chẳng hạn, `System.console()` có thể trả `null` nếu cách khởi chạy không cung cấp console.

Đọc tài liệu theo **phương thức đang dùng**, không chỉ nhìn nhãn `Since` của lớp: API của một lớp có thể được bổ sung qua nhiều phiên bản. Ví dụ, các phương thức mới trên một lớp lâu đời không tự trở thành tính năng Java 6.

Tham khảo hiện hành: [NavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html), [ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html), [ToolProvider](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html), [ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html), [Console](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Console.html).

## 3. Chuẩn bị môi trường và một thư mục riêng

Mở terminal tại thư mục thực hành. Kiểm tra:

```powershell
java -version
javac -version
Get-Command java
Get-Command javac
```

Cần `java` và `javac` trỏ tới JDK đã chọn. Terminal và IDE có thể chọn JDK khác nhau; hãy kiểm tra cả SDK của dự án và cấu hình chạy nếu kết quả giữa hai nơi khác nhau.

Tạo thư mục đầu ra:

```powershell
New-Item -ItemType Directory -Force out, generated | Out-Null
```

Bố trí cuối cùng:

```text
java6-api-practice/
├── CollectionsPractice.java
├── CompilerPractice.java
├── GeneratedHello.java
├── out/
└── generated/
```

Lưu tệp bằng UTF-8 không BOM. Những tệp Java trong bài không khai báo package để tập trung vào API, và mỗi lớp `public` có tệp trùng tên.

`out` chứa chương trình thực hành. `generated` chứa kết quả do Compiler API tạo trong thí nghiệm thứ hai.

## 4. Thí nghiệm một: tìm mốc và chọn đúng đầu cấu trúc dữ liệu

### 4.1. Bài toán trước khi viết mã

Có ba ngưỡng:

```text
0  -> START
50 -> PASS
80 -> DISTINCTION
```

Với điểm `75`, ngưỡng lớn nhất không vượt quá điểm là `50`. Với một danh sách công việc, thêm A trước B và xử lý theo thứ tự đến là FIFO. Với lịch sử hoàn tác, thao tác mới nhất cần được lấy ra trước, là LIFO.

Đây là ba yêu cầu khác nhau; ta dùng API thể hiện rõ yêu cầu thay vì tự viết vòng lặp tìm kiếm và quản lý chỉ số.

### 4.2. Chương trình hoàn chỉnh

Tệp `CollectionsPractice.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NavigableMap;
import java.util.TreeMap;

public class CollectionsPractice {
    public static void main(String[] args) {
        NavigableMap<Integer, String> grades = new TreeMap<>();
        grades.put(0, "START");
        grades.put(50, "PASS");
        grades.put(80, "DISTINCTION");
        System.out.println("floor(75)=" + grades.floorEntry(75));
        System.out.println("ceiling(75)=" + grades.ceilingEntry(75));
        System.out.println("lower(50)=" + grades.lowerKey(50));
        System.out.println("floor(50)=" + grades.floorKey(50));
        System.out.println("floor(-1)=" + grades.floorEntry(-1));

        Deque<String> queue = new ArrayDeque<>();
        queue.addLast("A");
        queue.addLast("B");
        System.out.println("queue=" + queue.pollFirst() + "," + queue.pollFirst());
        System.out.println("empty=" + queue.pollFirst());

        Deque<String> undo = new ArrayDeque<>();
        undo.push("edit-1");
        undo.push("edit-2");
        System.out.println("undo=" + undo.pop() + "," + undo.pop());
    }
}
```

Biên dịch và chạy:

```powershell
javac --release 17 -d out CollectionsPractice.java
java -cp out CollectionsPractice
```

Stdout:

```text
floor(75)=50=PASS
ceiling(75)=80=DISTINCTION
lower(50)=0
floor(50)=50
floor(-1)=null
queue=A,B
empty=null
undo=edit-2,edit-1
```

Kết quả đã được kiểm chứng trên JDK 21 nêu ở đầu bài.

### 4.3. Đọc kết quả theo hợp đồng

`floorEntry(75)` tìm mục có khóa lớn nhất **nhỏ hơn hoặc bằng** `75`. `ceilingEntry(75)` tìm mục có khóa nhỏ nhất **lớn hơn hoặc bằng** `75`.

`lowerKey(50)` loại trừ chính `50`, còn `floorKey(50)` cho phép bằng. Đó là lý do kết quả lần lượt là `0` và `50`.

`floorEntry(-1)` trả `null` vì không có ngưỡng phù hợp. Trong mã sử dụng thực tế, phải xử lý trường hợp này trước khi gọi `getValue()` trên kết quả. Xem [các quan hệ điều hướng của NavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html).

Với deque:

| Mục đích | Thêm | Lấy ra |
| --- | --- | --- |
| FIFO | `addLast` | `pollFirst` |
| LIFO | `push` | `pop` |

`pollFirst()` trả `null` khi rỗng, còn `pop()` khi rỗng gây ngoại lệ. `ArrayDeque` không cho phần tử `null` và không tự bảo đảm an toàn cho truy cập đồng thời. Vì vậy, chương trình mẫu dùng một luồng và lấy đúng số phần tử đã thêm.

Phép nối chuỗi trong các dòng in được đánh giá từ trái sang phải, nên hai lần lấy phần tử diễn ra theo thứ tự quan sát được. Xem [ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html).

Bài học ứng dụng là lựa chọn theo ngữ nghĩa: dùng cấu trúc có thứ tự để tìm mốc, và dùng đúng đầu deque theo yêu cầu xử lý.

## 5. Thí nghiệm hai: gọi trình biên dịch bằng API

### 5.1. Cơ chế cần quan sát

Thông thường terminal gọi `javac`. Trong một công cụ viết bằng Java, có thể lấy `JavaCompiler` rồi gửi yêu cầu biên dịch qua API:

```text
CompilerPractice đang chạy
        |
        v
ToolProvider.getSystemJavaCompiler()
        |
        v
biên dịch GeneratedHello.java
        |
        v
generated/GeneratedHello.class
        |
        v
lệnh java riêng chạy lớp đã biên dịch
```

Biên dịch và chạy lớp là hai bước riêng. API không tự thực thi `main` của tệp vừa biên dịch.

### 5.2. Tệp sẽ được biên dịch

Tệp `GeneratedHello.java`:

```java
public class GeneratedHello {
    public static void main(String[] args) {
        System.out.println("compiled.by.api");
    }
}
```

### 5.3. Chương trình gọi compiler

Tệp `CompilerPractice.java`:

```java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class CompilerPractice {
    public static void main(String[] args) {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK with jdk.compiler is required");
        }
        int code = compiler.run(null, System.out, System.err,
                "--release", "17", "-d", "generated", "GeneratedHello.java");
        System.out.println("compile.exit=" + code);
        if (code != 0) {
            throw new IllegalStateException("Compilation failed");
        }
    }
}
```

`ToolProvider.getSystemJavaCompiler()` có thể trả `null` khi môi trường không cung cấp compiler. Trong JDK hiện đại, việc có module `jdk.compiler` là điều kiện liên quan; một runtime đã được rút gọn có thể không chứa nó. Xem [ToolProvider hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html).

Các đối số trong `compiler.run(...)` là các phần của yêu cầu biên dịch. Đường dẫn được tính từ thư mục làm việc hiện tại của chương trình, không phải tự động từ thư mục chứa tệp `.class`.

### 5.4. Dựng và thực hiện hai bước

```powershell
javac --release 17 -d out CompilerPractice.java
java -cp out CompilerPractice
java -cp generated GeneratedHello
```

Stdout của lệnh chạy `CompilerPractice`:

```text
compile.exit=0
```

Stdout của lệnh chạy `GeneratedHello`:

```text
compiled.by.api
```

Các kết quả trên đã được kiểm chứng trên Microsoft OpenJDK 21.0.9. Chỉ chạy lớp đầu ra sau khi biên dịch thành công; nếu compiler báo lỗi, xem chẩn đoán và mã thoát thay vì chạy một tệp `.class` cũ còn sót.

Thử sửa `GeneratedHello.java` thành mã sai cú pháp rồi chạy lại `CompilerPractice`. Mục tiêu quan sát là compiler trả mã khác `0`, in chẩn đoán và chương trình báo thất bại. Không nên ghi cố định toàn bộ thông báo lỗi vì nội dung chẩn đoán có thể khác theo JDK và ngôn ngữ môi trường.

## 6. Dùng --release để đặt mức nền, không để “biến JDK thành Java 6”

`--release 17` yêu cầu biên dịch cho mức nền Java 17 được công cụ hỗ trợ, bao gồm quy tắc ngôn ngữ, class file và tập API nền tương ứng. Xem [tài liệu javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html#option-release).

Trong bài, nó tạo một ranh giới biên dịch rõ ràng; API trọng tâm vẫn có thể có nguồn gốc cũ hơn. Một số cú pháp của ví dụ như dấu `<>` khi khởi tạo generic xuất hiện sau Java 6, và `--release` cũng là công cụ của JDK mới. Chúng là phần hạ tầng thực hành hiện đại, không được gán lại thành tính năng Java 6.

Chỉ dùng những giá trị `--release` mà compiler đang chạy hỗ trợ. Không mặc định JDK hiện tại nhận `--release 6`. Mục tiêu bài này là vận dụng kiến thức còn hữu ích, không dựng chuỗi công cụ cũ.

Ngoài ra, `--release` không tự chọn phiên bản thư viện ngoài JDK và không thay cho việc kiểm thử hành vi trên runtime đích của dự án.

## 7. Đọc tài liệu API theo cách có thể kiểm chứng

Với mỗi API, lập một ghi chú nhỏ:

```text
Bài toán:
Lớp/interface được dùng:
Phương thức cụ thể:
Điều kiện đầu vào:
Kết quả khi không có dữ liệu:
Ngoại lệ quan trọng:
Điều kiện luồng/môi trường:
Lệnh chạy và stdout quan sát:
```

Ví dụ, với `floorEntry` phải ghi “có thể trả null”, còn với `ArrayDeque` phải ghi “không chứa null; không tự an toàn luồng”. Với compiler, phải ghi “môi trường phải cung cấp compiler; kết quả biên dịch cần được kiểm tra”.

Cách đọc này giúp kiến thức bền hơn việc thuộc danh sách tính năng theo năm phát hành.

Nếu mở rộng sang `ServiceLoader`, cần học cả cách phân phối nhà cung cấp dịch vụ và xử lý trường hợp không tìm thấy. Nếu mở rộng sang `Console`, cần kiểm tra kết quả `System.console()` trước khi dùng. Các chủ đề đó có giá trị hiện nay nhưng không cần chen toàn bộ vào hai thí nghiệm đã có.

## 8. Lỗi thường gặp khi học API cũ trên JDK mới

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| Terminal chạy được nhưng IDE không chạy được | JDK dự án và cấu hình chạy có trùng nhau không |
| Compiler API trả `null` | Runtime đang chạy có cung cấp `jdk.compiler` không |
| Không tìm thấy `GeneratedHello.java` | Thư mục làm việc có đúng nơi lưu mã nguồn không |
| Chạy lại vẫn thấy output cũ sau một lỗi biên dịch | Có đang chạy class file của lượt thành công trước không |
| `floorEntry` gây lỗi ở bước đọc giá trị | Đã xử lý kết quả `null` chưa |
| Deque cho thứ tự ngược dự kiến | Đã chọn cặp thao tác FIFO hay LIFO đúng chưa |
| Thấy API có `Since: 1.6` nên nghĩ mọi phương thức đều có từ Java 6 | Kiểm tra tài liệu từng phương thức |
| Một ví dụ hiện đại dùng được nên suy ra chạy được trên JDK 6 | Tách mức cú pháp/API biên dịch khỏi nguồn gốc API |

## 9. Bài tập nối tiếp

1. Đổi điểm tra cứu thành `50`, `80`, `100`; dự đoán `floorEntry` và `ceilingEntry` trước khi chạy.
2. Thêm C vào hàng đợi, rồi giải thích vì sao FIFO trả A trước còn ngăn xếp trả phần tử mới nhất trước.
3. Cho compiler biên dịch một lớp in thông điệp khác và chỉ chạy lớp sau khi nhận `compile.exit=0`.
4. Ghi rõ trong báo cáo cá nhân: API có nguồn gốc từ đâu, dùng compiler nào và chạy JVM nào.
5. Chọn một API mở rộng như `ServiceLoader` hoặc `Console`, viết ra điều kiện môi trường cần kiểm tra trước khi dùng.

Một bài thực hành thành công không chỉ là “mã chạy được”. Bạn cần giải thích API giải quyết bài toán gì, xử lý các trường hợp biên và chứng minh kết quả bằng lệnh chạy trên JDK phù hợp đang được duy trì.
