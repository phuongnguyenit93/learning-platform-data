# Thực hành trên JDK được hỗ trợ với nền tảng có nguồn gốc Java 8

## 1. Mục tiêu và nguyên tắc lựa chọn JDK

Bài này thực hành các tính năng **xuất hiện trong Java 8 nhưng vẫn được sử dụng trong Java hiện đại**: biểu thức lambda, functional interface, Stream API, Optional, java.time và CompletableFuture. Mục tiêu là hiểu và chạy được chúng trên một **JDK đang được nhà cung cấp cập nhật**, đồng thời biết khi nào cần giữ tương thích ngược với Java 8.

Tính đến tháng 11/2026, **Java 25 là phiên bản LTS mới nhất**; Java 21 vẫn thuộc dòng LTS có hỗ trợ. Bạn có thể chọn bản phân phối OpenJDK được duy trì hoặc JDK do tổ chức phê duyệt. Chính sách cập nhật bảo mật, giấy phép và thời hạn hỗ trợ khác nhau theo nhà cung cấp; việc dùng một bản LTS không thay thế trách nhiệm cài bản vá.

**Phân biệt:**
- *Nguồn gốc Java 8*: API hoặc cú pháp ra đời trong Java 8, vẫn hữu ích hiện nay.
- *JDK dùng để phát triển*: bộ công cụ thực tế đang cài, ví dụ JDK 21/25.
- *Phiên bản Java tối thiểu khi chạy*: hợp đồng tương thích của artifact, do dự án quyết định.
- *Runtime được hỗ trợ*: bản phát hành cụ thể còn được cung cấp cập nhật, khác với việc một đoạn bytecode về lý thuyết chạy được.

Bài này ưu tiên API còn áp dụng hiện nay. Không dùng applet, Java Web Start, API nội bộ `sun.*` hoặc hướng dẫn triển khai đã lỗi thời.

### Chuẩn bị và kiểm tra

Cài **JDK** thay vì chỉ cài runtime, rồi mở terminal PowerShell, Command Prompt hoặc shell Unix:

~~~text
java -version
javac -version
javac --help
~~~

`java` khởi chạy JVM; `javac` biên dịch nguồn Java; `javac --help` cho biết các mức tương thích mà compiler hiện tại chấp nhận. Đừng mặc định hai lệnh trỏ đến cùng một phiên bản JDK: kiểm tra `JAVA_HOME`, `PATH`, JDK của IDE, toolchain của hệ build và CI nếu kết quả khác mong đợi. Chạy lại terminal sau khi sửa biến môi trường.

## 2. Hiểu ba lớp tương thích

| Lớp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Cú pháp nguồn | Compiler hiểu cấu trúc ngôn ngữ nào | Lambda `task -> task.priority` thuộc Java 8 |
| API | Những lớp và phương thức được phép gọi | `LocalDate`, `Collectors.toList()` có từ Java 8; `Stream.toList()` có từ Java 16 |
| Bytecode/JVM | File `.class` yêu cầu JVM tối thiểu nào | Java 8 là major version 52; Java 21 là 65; Java 25 là 69 |

Khi dùng JDK hiện đại mà **cần tạo mã tương thích API/bytecode Java 8**, chọn:

~~~text
javac --release 8 Java8Practice.java
~~~

`--release 8` kiểm tra cú pháp, API được phép và định dạng class của bản Java đích. Nó đáng tin cậy hơn việc chỉ kết hợp `-source 8 -target 8`, vì chỉ đặt source/target có thể bỏ sót việc vô tình gọi API mới. Giá trị `--release` được hỗ trợ tùy phiên bản compiler; kiểm tra `javac --help`.

Điều này **không bảo đảm** thư viện bên thứ ba, JVM option, dữ liệu ngoài, hành vi hệ điều hành và mọi đường chạy thực sự tương thích. Muốn hỗ trợ runtime đích phải kiểm thử cả artifact và các phụ thuộc trên môi trường tương ứng. Nếu ứng dụng mới chỉ triển khai trên JDK 21/25, không cần hạ mục tiêu về Java 8 chỉ vì đang học các API ra đời từ Java 8.

## 3. Bài thực hành tích hợp chạy độc lập

Tạo file **`Java8Practice.java`**. Chương trình xử lý danh sách công việc: lọc việc có độ ưu tiên từ 5, sắp theo hạn, lấy hạn gần nhất, tính khoảng cách ngày và thực thi phép tính bất đồng bộ.

~~~java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

public class Java8Practice {
    private static final class Task {
        final String id;
        final int priority;
        final LocalDate deadline;

        Task(String id, int priority, String deadline) {
            this.id = id;
            this.priority = priority;
            this.deadline = LocalDate.parse(deadline);
        }
    }

    public static void main(String[] args) {
        List<Task> tasks = Arrays.asList(
            new Task("A", 3, "2026-11-10"),
            new Task("C", 8, "2026-11-12"),
            new Task("B", 5, "2026-11-11")
        );

        List<String> selected = tasks.stream()
            .filter(task -> task.priority >= 5)
            .sorted(Comparator.comparing(task -> task.deadline))
            .map(task -> task.id)
            .collect(Collectors.toList());
        System.out.println("Ưu tiên: " + String.join(", ", selected));

        Optional<Task> nearest = tasks.stream()
            .min(Comparator.comparing(task -> task.deadline));
        String nearestId = nearest.map(task -> task.id)
            .orElse("không có");
        System.out.println("Gần nhất: " + nearestId);

        long days = ChronoUnit.DAYS.between(
            LocalDate.parse("2026-11-10"),
            LocalDate.parse("2026-11-12"));
        System.out.println("Số ngày: " + days);

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<Integer> result =
                CompletableFuture.supplyAsync(
                    () -> tasks.stream()
                        .mapToInt(task -> task.priority).sum(),
                    executor
                ).thenApply(sum -> sum * 2);

            int doubled = result.join();
            System.out.println("Điểm nhân đôi: " + doubled);

            if (!selected.equals(Arrays.asList("B", "C"))
                    || !"A".equals(nearestId)
                    || days != 2
                    || doubled != 32) {
                throw new AssertionError("Kết quả không đúng");
            }
            System.out.println("Kiểm tra: PASS");
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch/chạy từ chính thư mục chứa file trên một JDK mới có hỗ trợ `--release 8`:

~~~text
javac --release 8 -encoding UTF-8 Java8Practice.java
java Java8Practice
~~~

Nếu chương trình chỉ nhắm runtime của JDK đang cài, cũng có thể biên dịch `javac -encoding UTF-8 Java8Practice.java`. Tham số `-encoding UTF-8` bảo đảm đọc file nguồn tiếng Việt theo UTF-8; chú ý lưu file bằng chính encoding đó. Lệnh `java Java8Practice` giả định `Java8Practice.class` nằm trong thư mục hiện hành.

**Stdout chính xác:**

~~~text
Ưu tiên: B, C
Gần nhất: A
Số ngày: 2
Điểm nhân đôi: 32
Kiểm tra: PASS
~~~

### Giải thích theo từng bước

**Lambda + Stream:** `filter` giữ B và C (priority 5 và 8). `sorted(Comparator.comparing(...))` sắp theo hạn: B (11/11) trước C (12/11); `map` biến đối tượng thành ID; `collect(Collectors.toList())` tạo danh sách kết quả. Stream có các bước trung gian thường thực thi lười; `collect` là thao tác kết thúc. Không tái sử dụng Stream đã bị tiêu thụ.

**Optional:** `min` trả `Optional<Task>` vì danh sách có thể rỗng. `nearest.map(...).orElse(...)` diễn đạt cả hai trường hợp. `get()` mà không kiểm tra `isPresent()` dễ ném `NoSuchElementException`; chỉ gọi `orElseThrow` khi vắng mặt là lỗi nghiệp vụ.

**java.time:** `LocalDate.parse` đọc ngày ISO-8601 và tạo kiểu ngày không gắn múi giờ. `ChronoUnit.DAYS.between` cho kết quả 2 ngày. Khi lưu mốc thời gian toàn cầu, dùng `Instant`; khi xử lý giờ địa phương theo vùng, chọn `ZoneId`/`ZonedDateTime`. Không quy đổi ngày lịch bằng cách tự chia mili-giây cho 86.400.000 khi có múi giờ/DST.

**CompletableFuture:** `supplyAsync` chạy hàm trên executor đã chỉ định; `thenApply` áp phép biến đổi sau khi có kết quả; `join()` đợi và lấy giá trị. Tổng priority 3 + 8 + 5 = 16, nhân 2 = 32. `finally` đóng executor, tránh thread pool tồn tại sau chương trình.

**Kiểm tra:** các điều kiện `if` ném `AssertionError` nếu sai, không phụ thuộc cấu hình bật/tắt JVM assertions. Trong ứng dụng thực tế, chuyển các kiểm tra này thành test JUnit và kiểm thử cả tình huống rỗng, dữ liệu lỗi, lỗi đồng thời.

## 4. Bài tập mở rộng có kết quả xác định

### 4.1. Đếm việc ưu tiên

Thêm **bên trong `main`**, ngay trước khối tạo `executor`:

~~~java
long highPriorityCount = tasks.stream()
    .filter(task -> task.priority >= 5)
    .count();
System.out.println("Số việc ưu tiên: " + highPriorityCount);
~~~

Dòng mới phải là `Số việc ưu tiên: 2`. `count` là terminal operation; filter nên là predicate không có side effect.

### 4.2. Phân nhóm bằng Collector

Thêm `import java.util.Map;` ở đầu file, rồi đặt đoạn sau trong `main`:

~~~java
Map<Boolean, Long> counts = tasks.stream()
    .collect(Collectors.partitioningBy(
        task -> task.priority >= 5,
        Collectors.counting()
    ));
System.out.println("Nhóm ưu tiên: " + counts.get(true));
~~~

Kết quả: `Nhóm ưu tiên: 2`. `partitioningBy` chia đúng hai nhóm true/false; khi khóa là ID/chủ đề thay vì điều kiện boolean, cân nhắc `groupingBy`. Đoạn mã này là **một phần bổ sung**, không phải file độc lập.

### 4.3. Trường hợp không có dữ liệu

Thay `tasks` bằng danh sách rỗng có kiểu phù hợp, `nearest` trở thành `Optional.empty()` và `nearestId` bằng `không có`. Tuy nhiên, các dòng in, kết quả đếm và kiểm tra cuối sẽ đổi theo; hãy cập nhật các điều kiện test tương ứng. Trong nghiệp vụ, dùng giá trị dự phòng chỉ khi thiếu dữ liệu là trạng thái hợp lệ; trường hợp bắt buộc phải tồn tại có thể dùng `orElseThrow(() -> new IllegalStateException("Không có tác vụ"))`.

### 4.4. Xử lý lỗi bất đồng bộ

Trong khối `try` khi `executor` còn sống, có thể minh họa cách biến lỗi thành giá trị dự phòng:

~~~java
CompletableFuture<Integer> safe = CompletableFuture
    .<Integer>supplyAsync(() -> {
        throw new IllegalStateException("Nguồn dữ liệu lỗi");
    }, executor)
    .exceptionally(error -> -1);
System.out.println("Giá trị dự phòng: " + safe.join());
~~~

Dòng mới: `Giá trị dự phòng: -1`. Vì lambda chỉ ném lỗi, `<Integer>` cho biết kiểu dự kiến để `exceptionally` nhận đúng kiểu. Đây là **đoạn bổ sung vào chương trình**, không phải chương trình độc lập. Khi không có `exceptionally` hoặc `handle` xử lý, `join` báo `CompletionException` bao lấy nguyên nhân. Chọn fallback hay ném lỗi tiếp theo quy tắc nghiệp vụ; đừng che lỗi hệ thống bằng giá trị mặc định tùy tiện.

## 5. Đặt target Java cho ứng dụng thực tế

### Hai trường hợp cần tách bạch

**A. Ứng dụng mới dùng JDK 21/25:** dùng toolchain và `release` tương ứng với runtime triển khai. Các API Java 8 vẫn chạy trên JVM mới. Không hạn chế source về Java 8 khi sản phẩm không yêu cầu tương thích Java 8.

**B. Thư viện/ứng dụng phải còn tương thích Java 8:** biên dịch theo `--release 8`, kiểm tra thư viện phụ thuộc cũng hỗ trợ runtime 8, kiểm tra class version và chạy test tích hợp trên runtime đích có hỗ trợ phù hợp. Đừng thử nghiệm trên một JVM cũ không được cập nhật trong môi trường production.

Để xem bytecode được sinh ra:

~~~text
javap -verbose Java8Practice
~~~

Tìm `major version: 52` khi đã dùng `--release 8`; đối với output mặc định của JDK 21, giá trị là 65, và mặc định JDK 25 là 69. Khác biệt này liên quan đến **mức runtime tối thiểu**, không nói rằng code hiện đại không thể dùng các API nguồn gốc Java 8.

### Cấu hình Gradle theo toolchain

Trong `build.gradle` dùng plugin Java, với toolchain JDK 25 và mục tiêu Java 8, có thể dùng:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
}
~~~

Đoạn trên là cấu hình **Gradle Groovy DSL**, không phải mã Java. Nếu project dùng JDK 21, đặt toolchain 21. Bản Gradle đang dùng phải hỗ trợ JDK/toolchain chọn; kiểm tra ma trận tương thích của Gradle. Đối với dự án mới chạy runtime JDK 25, thay `options.release = 8` thành mức runtime dự kiến, chẳng hạn 25; không giữ 8 theo thói quen.

Với Maven Compiler Plugin hiện hành, có thể đặt property dưới phần `<properties>` của `pom.xml`:

~~~xml
<maven.compiler.release>8</maven.compiler.release>
~~~

Đây là một phần tử cấu hình, không phải một file POM hoàn chỉnh. Giá trị 8 chỉ đúng khi dự án có hợp đồng tương thích 8; Maven, plugin và toolchain phải đủ mới để hỗ trợ JDK được chọn.

## 6. Các lỗi dễ gặp và cách phân tích

| Dấu hiệu | Nguyên nhân khả dĩ | Thao tác kiểm chứng |
| --- | --- | --- |
| `javac` không được nhận diện | Chưa cài JDK hoặc PATH chưa đúng | Kiểm tra JDK và PATH, mở terminal mới |
| `java` và `javac` khác phiên bản | Nhiều JDK trên máy | Kiểm tra đường dẫn thực thi, JAVA_HOME, cấu hình IDE/CI |
| `UnsupportedClassVersionError` | JVM chạy cũ hơn bytecode được biên dịch | Kiểm tra runtime và major version, cấu hình release đúng |
| `cannot find symbol` với `--release 8` | Mã gọi API xuất hiện sau Java 8 | Chọn API tương thích hoặc nâng target có chủ đích |
| `NoSuchMethodError` lúc chạy | Version thư viện khi chạy khác khi biên dịch | Kiểm tra dependency tree và artifact thực thi |
| Kết quả Stream không như dự kiến | Sai comparator, thứ tự dữ liệu hoặc side effect | Kiểm tra từng phép biến đổi bằng dữ liệu mẫu |
| Ứng dụng không kết thúc | Executor không shutdown hoặc tác vụ đang treo | Đóng pool, áp timeout phù hợp, quan sát thread |
| Lỗi class không tìm thấy khi nâng JDK | Phụ thuộc vào thành phần không còn nằm trong runtime | Chỉ định dependency được bảo trì và cập nhật cấu hình |

Một chương trình chạy được trong IDE chưa đủ để khẳng định sản phẩm tương thích. Kiểm tra lệnh build sạch, dependency, unit/integration test và runtime chạy trong CI. Không tắt cơ chế kiểm tra mô-đun hoặc truy cập API nội bộ chỉ để bỏ qua lỗi khi nâng JDK.

## 7. Nguyên tắc sử dụng kiến thức Java 8 còn phù hợp hiện nay

1. **Lambda là công cụ diễn đạt hành vi**, không phải mục tiêu làm code ngắn bằng mọi giá. Đặt tên biến và viết hàm có nghĩa; ưu tiên dễ đọc.
2. **Stream phục vụ biến đổi dữ liệu rõ ràng.** Không dùng `parallelStream()` mặc định với hy vọng nhanh hơn: đo hiệu năng và xét common pool, khối lượng công việc, dữ liệu chia sẻ, I/O blocking.
3. **Optional diễn đạt giá trị có thể vắng mặt.** Không thay toàn bộ field và tham số bằng Optional, và không dùng `get()` khi không kiểm tra.
4. **java.time có ngữ nghĩa từng kiểu.** `LocalDate` cho ngày, `Instant` cho thời điểm, `ZonedDateTime` cho logic theo múi giờ. Xác định timezone khi nhập/xuất dữ liệu.
5. **CompletableFuture cần quản lý lỗi và tài nguyên.** Xác định executor, chính sách timeout/cancel và logging; nó không tự bảo đảm retry, transaction hay hiệu năng cao hơn.
6. **Tương thích có ba lớp.** Khi dùng API sau Java 8, ghi rõ mức Java yêu cầu; khi cần runtime cũ, kiểm tra cả dependencies và bytecode bằng build/test.
7. **Giữ stack được hỗ trợ.** Cập nhật bản vá JDK, Gradle/Maven và thư viện; không sử dụng cơ chế triển khai và API đã lỗi thời.
8. **Dùng test để xác minh.** Có ca dữ liệu rỗng, dữ liệu sai, ngày không hợp lệ, lỗi bất đồng bộ và build trên runtime thực tế.

## 8. Bài tự đánh giá

- Tạo thêm trường `owner` trong `Task`, dùng `groupingBy` đếm việc theo người phụ trách. Khi kiểm tra output, không phụ thuộc thứ tự duyệt `HashMap`.
- Thử không có task và chứng minh `Optional` trả giá trị dự phòng thay vì lỗi. Viết lại điều kiện test theo trạng thái mới.
- Đưa vào chuỗi ngày không hợp lệ, phân biệt lỗi parse với thiếu dữ liệu nghiệp vụ và chọn vị trí xác thực đầu vào.
- Đổi xử lý bất đồng bộ thành trường hợp có lỗi; giải thích khi nào dùng `exceptionally`, `handle` hoặc cho exception lan lên.
- Biên dịch cùng file một lần với target mặc định, một lần với `--release 8`; dùng `javap -verbose` xác minh major version và nêu hệ quả đối với JVM chạy.

**Đạt yêu cầu** khi bạn chạy chương trình trên JDK được duy trì, đầu ra khớp bản mẫu, giải thích được dữ liệu chảy qua Stream/Optional/CompletableFuture, xác định được API nào có sau Java 8 và biết chọn target phù hợp với runtime thực sự.

## Nguồn chính thức để đối chiếu

- Lộ trình hỗ trợ Java SE: https://www.oracle.com/java/technologies/java-se-support-roadmap.html
- Tài liệu theo từng phiên bản Java SE: https://docs.oracle.com/en/java/javase/
- Trình biên dịch `javac` và tùy chọn `--release`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- Hướng dẫn nâng JDK: https://docs.oracle.com/en/java/javase/25/migrate/preparing-migration.html

Tra cứu tài liệu của **chính phiên bản JDK và bản phân phối đang sử dụng** trước khi chọn API mới, nâng toolchain hoặc thay đổi target triển khai.