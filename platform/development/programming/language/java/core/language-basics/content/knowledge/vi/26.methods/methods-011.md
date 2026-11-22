# Tách bài toán thành các phương thức có trách nhiệm rõ ràng — Java 17+

## 1. Vì sao cần tách phương thức?

Khi một phương thức vừa kiểm tra đầu vào, vừa tính toán, vừa xếp loại, vừa in kết quả, người đọc phải theo dõi **nhiều mục đích cùng lúc**. Khi yêu cầu thay đổi, dễ sửa nhầm logic không liên quan.

Một phương thức có **trách nhiệm rõ ràng** nên mô tả được bằng một hành động cụ thể: `validateScores` kiểm tra dữ liệu, `calculateAverage` tính trung bình, `classify` xếp loại, `formatReport` tạo chuỗi và `showCase` hiển thị.

**Nguyên tắc thực hành:** một phương thức nên có **một lý do chính để thay đổi**, chứ không nhất thiết chỉ có một dòng lệnh. Tách theo ý nghĩa nghiệp vụ, không chia vụn mọi phép gán hay phép cộng.

Ví dụ bài toán: nhận tên học viên và mảng điểm nguyên (0–100), tính trung bình **lấy phần nguyên**, xếp loại và xuất một dòng báo cáo. Nếu đầu vào sai, báo lỗi rõ ràng.

## 2. Phân rã bài toán thành các bước

| Trách nhiệm | Phương thức | Đầu vào → đầu ra |
|---|---|---|
| Kiểm tra tên | `requireName` | `String` → `String` đã bỏ khoảng trắng đầu/cuối hoặc ném lỗi |
| Kiểm tra danh sách điểm | `validateScores` | `int[]` → `void` hoặc ném lỗi |
| Tính điểm trung bình | `calculateAverage` | `int[]` hợp lệ → `int` |
| Xếp loại | `classify` | `int average` → `String` |
| Tạo kết quả | `formatReport` | Tên, số môn, trung bình, xếp loại → `String` |
| Phối hợp các bước | `buildReport` | Tên + điểm → chuỗi hoàn chỉnh |
| Hiển thị / xử lý lỗi | `showCase` | Dữ liệu mẫu → in báo cáo hoặc lỗi |

~~~mermaid
flowchart TD
    A["showCase"] --> B["buildReport"]
    B --> C["requireName"]
    B --> D["validateScores"]
    B --> E["calculateAverage"]
    B --> F["classify"]
    B --> G["formatReport"]
    G --> H["Chuỗi kết quả"]
    H --> A
    A --> I["System.out.println"]
~~~

`buildReport` là phương thức **điều phối**: gọi các phương thức nhỏ theo đúng trình tự, không tự lặp lại công thức tính điểm hoặc xếp loại. Đây là cách tách hợp lý giữa “biết cần làm gì” và “biết một bước làm như thế nào”.

## 3. Xác định hợp đồng của từng phương thức

Trước khi code, hãy ghi rõ **đầu vào, đầu ra và tình huống lỗi**:

- `requireName(name)`: từ chối `null` hoặc chỉ toàn khoảng trắng; tên hợp lệ được `strip()`.
- `validateScores(scores)`: từ chối `null`, mảng rỗng, điểm ngoài khoảng 0–100; không sửa mảng.
- `calculateAverage(scores)`: giả định dữ liệu **đã được kiểm tra**, tính tổng bằng `long`, chia nguyên cho số môn. Ví dụ `(70 + 71) / 2 = 70`.
- `classify(avg)`: `avg >= 80` → `GOOD`; `avg >= 50` → `PASS`; còn lại → `RETRY`.
- `formatReport(...)`: chỉ ghép chuỗi, không in và không thay dữ liệu.
- `buildReport(...)`: trả chuỗi; nếu dữ liệu sai, cho phép `IllegalArgumentException` đi lên caller.

Mỗi phương thức nên có **tên động từ rõ nghĩa**, kiểu trả về đúng công việc, và không thay đổi trạng thái ngoài ý muốn. `validateScores` là `void` vì nhiệm vụ của nó là **xác thực hoặc báo lỗi**, không phải tính tổng.

**Cảnh báo về tính toán:** sử dụng `long` để cộng các giá trị `int` hạn chế tràn tổng; với dữ liệu điểm 0–100 và độ dài mảng Java hợp lệ, `long` đủ chứa tổng. Trung bình ở đây là **phép chia nguyên có chủ đích**, không phải làm tròn số thực.

## 4. Tách tính toán khỏi tác dụng phụ

Một hàm như:

~~~java
static int classify(int average) {
    // SAI về ý nghĩa ví dụ: vừa quyết định xếp loại vừa in, khó tái sử dụng.
    System.out.println("classifying");
    return average >= 50 ? 1 : 0;
}
~~~

trộn **kết quả tính toán** với **ghi ra màn hình**. Nó khó dùng khi sau này phải ghi vào file, trả JSON hoặc chạy test không mong đợi stdout.

Cách tách:

~~~java
static String classify(int average) {
    if (average >= 80) return "GOOD";
    if (average >= 50) return "PASS";
    return "RETRY";
}

// Gọi: chỉ khi phần giao diện cần hiển thị
System.out.println(classify(75)); // PASS
~~~

`classify` không phụ thuộc `Scanner`, `System.out` hay nơi hiển thị kết quả. Cùng một đầu vào cho cùng kết quả, dễ thử các biên 49/50/79/80.

**Một phương thức không cần “thuần” tuyệt đối mới có trách nhiệm rõ ràng.** Việc in thông báo là trách nhiệm hợp lệ của `showCase`; cần tránh để nó xen lẫn công thức tính.

## 5. `private`, `static` và việc tái sử dụng

Trong ví dụ, các bước nội bộ được khai báo `private static`:

~~~java
private static int calculateAverage(int[] scores) { /* ... */ }
~~~

- `private`: giới hạn nơi có thể gọi từ ngoài lớp, tránh làm lộ chi tiết triển khai thành API.
- `static`: công việc không cần trạng thái instance, có thể gọi từ phương thức `static` cùng lớp.
- Kiểu tham số / kiểu trả về tạo **hợp đồng** giúp compiler kiểm tra cách gọi.

Không phải tất cả các phương thức trong mọi chương trình đều nên `static`: khi trách nhiệm thật sự gắn với trạng thái một đối tượng, instance method có thể phù hợp hơn. Bài này dùng `static` vì ví dụ xử lý dữ liệu đầu vào và trả kết quả không cần object chuyên biệt.

**Tránh trùng lặp:** nếu ba nơi đều kiểm tra `score >= 80`, hãy dùng chung một `classify`; khi đổi ngưỡng, chỉ phải sửa một nơi. Nhưng đừng tạo hàng chục phương thức một dòng chỉ để “đủ số lượng hàm”.

## 6. Chương trình Java 17+ hoàn chỉnh

Lưu file đúng tên **`ClearMethodResponsibilitiesDemo.java`**:

~~~java
public final class ClearMethodResponsibilitiesDemo {
    private ClearMethodResponsibilitiesDemo() {}

    // Trách nhiệm 1: kiểm tra và chuẩn hóa tên.
    private static String requireName(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return name.strip();
    }

    // Trách nhiệm 2: xác thực điểm, không tính toán.
    private static void validateScores(int[] scores) {
        if (scores == null || scores.length == 0) {
            throw new IllegalArgumentException("scores must not be null or empty");
        }
        for (int i = 0; i < scores.length; i++) {
            if (scores[i] < 0 || scores[i] > 100) {
                throw new IllegalArgumentException(
                        "score at index " + i + " must be 0..100");
            }
        }
    }

    // Trách nhiệm 3: tính trung bình, giả định đã validate.
    private static int calculateAverage(int[] scores) {
        long sum = 0;
        for (int score : scores) {
            sum += score;
        }
        return (int) (sum / scores.length);
    }

    // Trách nhiệm 4: áp dụng duy nhất quy tắc xếp loại.
    private static String classify(int average) {
        if (average >= 80) return "GOOD";
        if (average >= 50) return "PASS";
        return "RETRY";
    }

    // Trách nhiệm 5: định dạng; không in ra màn hình.
    private static String formatReport(
            String name, int count, int average, String level) {
        return name + " | count=" + count
                + " | avg=" + average + " | level=" + level;
    }

    // Điều phối luồng nghiệp vụ, không nhân đôi công thức.
    public static String buildReport(String name, int[] scores) {
        String cleanName = requireName(name);
        validateScores(scores);
        int average = calculateAverage(scores);
        String level = classify(average);
        return formatReport(cleanName, scores.length, average, level);
    }

    // Ranh giới hiển thị: in kết quả và xử lý đầu vào không hợp lệ.
    private static void showCase(String name, int[] scores) {
        try {
            System.out.println(buildReport(name, scores));
        } catch (IllegalArgumentException ex) {
            System.out.println("ERROR: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        showCase(" An ", new int[]{90, 80, 70});
        showCase("Binh", new int[]{40, 50, 60, 50});
        showCase("Chi", new int[]{30, 40});
        showCase("Dung", new int[]{});
        showCase("Em", new int[]{90, 101});
        showCase("", new int[]{90});
        showCase("Phuc", null);
        showCase("Giang", new int[]{100});
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên, terminal đặt tại thư mục chứa file. Chương trình chỉ dùng Java chuẩn, không cần thư viện ngoài, Maven/Gradle hoặc preview feature.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ClearMethodResponsibilitiesDemo.java
java -cp . ClearMethodResponsibilitiesDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ClearMethodResponsibilitiesDemo.java
java -cp . ClearMethodResponsibilitiesDemo
~~~

### Exact expected stdout

~~~text
An | count=3 | avg=80 | level=GOOD
Binh | count=4 | avg=50 | level=PASS
Chi | count=2 | avg=35 | level=RETRY
ERROR: scores must not be null or empty
ERROR: score at index 1 must be 0..100
ERROR: name must not be blank
ERROR: scores must not be null or empty
Giang | count=1 | avg=100 | level=GOOD
~~~

Đọc theo luồng: `showCase` gọi `buildReport`, nơi này kiểm tra tên và điểm trước khi tính. Ví dụ `Em` chứa điểm 101 nên bị từ chối **trước** bước tính trung bình; dữ liệu sai không bị âm thầm thay thế bằng giá trị 0.

## 7. Kiểm thử theo trách nhiệm và trường hợp biên

Khi đã tách phương thức, có thể kiểm tra mỗi nhóm yêu cầu riêng:

| Nội dung cần kiểm | Input | Expected |
|---|---|---|
| Tên | `" An "` | `"An"` |
| Điểm hợp lệ | `{90,80,70}` | Average `80`, level `GOOD` |
| Ngưỡng trên | Average `79` và `80` | `PASS`, `GOOD` |
| Ngưỡng dưới | Average `49` và `50` | `RETRY`, `PASS` |
| Điểm trung bình không nguyên | `{70,71}` | `70` theo quy tắc chia nguyên |
| Mảng rỗng/null | `{}`, `null` | `IllegalArgumentException` |
| Điểm ngoài biên | `{-1}`, `{101}` | `IllegalArgumentException` |

Ví dụ một kiểm tra đơn giản khi đặt trong cùng lớp:

~~~java
if (!"GOOD".equals(classify(80))) {
    throw new AssertionError("80 must be GOOD");
}
if (!"PASS".equals(classify(50))) {
    throw new AssertionError("50 must be PASS");
}
~~~

Đây là các ca kiểm tra logic, không phải ví dụ khác của câu lệnh `assert` (vốn tắt mặc định nếu không dùng `-ea`). Trong dự án lớn có thể sử dụng JUnit và unit test chuyên dụng; ví dụ chính cố ý không cần thư viện ngoài.

## 8. Mở rộng và lỗi thiết kế cần tránh

**Khi đổi quy tắc xếp loại** từ 80 thành 85, sửa `classify` và test liên quan, không phải sửa code xác thực hoặc in. Khi đổi giao diện xuất từ console sang web, tái sử dụng `buildReport` rồi thay tầng hiển thị.

| Dấu hiệu | Rủi ro | Cách cải thiện |
|---|---|---|
| Một method dài, gồm validate + tính + in | Khó đọc, khó test, khó sửa | Tách theo các mục tiêu riêng |
| `calculateAverage` tự gọi `System.out.println` | Phụ thuộc giao diện | Trả giá trị, để caller hiển thị |
| Nhiều nơi dùng cùng ngưỡng xếp loại | Logic không nhất quán | Tập trung vào `classify` |
| Method tên `process` không rõ kết quả | Người dùng API khó hiểu | Chọn tên như `buildReport`, `validateScores` |
| Hàm tính sửa `scores[i]` ngoài ý muốn | Caller nhìn thấy dữ liệu bị đổi | Tránh tác dụng phụ, ghi rõ hợp đồng |
| Tách mọi dòng lệnh thành một method | Code phân mảnh, phải nhảy liên tục | Tách theo **trách nhiệm thực sự** |
| Bắt mọi `Exception` trong hàm tính | Có thể che bug | Xử lý lỗi ở ranh giới thích hợp |
| Không xác định dữ liệu đầu vào hợp lệ | Dễ chia cho 0, trả sai | Kiểm tra trước khi tính |
| Để mọi helper thành `public` | Mở rộng API không cần thiết | Giữ `private` khi chỉ dùng trong lớp |

**Điểm cần cân nhắc:** `buildReport` hiện trả một chuỗi phục vụ một định dạng cố định. Khi ứng dụng phải hỗ trợ nhiều đầu ra phức tạp, có thể trả một đối tượng kết quả (ví dụ record Java 17), để tầng hiển thị định dạng sau. Đừng tăng độ phức tạp khi bài toán chưa cần.

## 9. Bài tập và đáp án

**Bài A.** Một method vừa nhập dữ liệu từ bàn phím, tính tổng, xếp loại và in. Hãy đề xuất cách tách.

**Đáp án:** `readInput` đọc dữ liệu; `validateInput` kiểm tra; `calculateTotal` tính; `classify` xếp loại; `formatReport` tạo chuỗi; `main` hoặc `showResult` phối hợp và hiển thị. Có thể gộp bước nhỏ nếu thật sự cùng một mục tiêu rõ ràng.

**Bài B.** Nếu thay ngưỡng `GOOD` từ 80 thành 85, nên sửa phương thức nào?

**Đáp án:** `classify` và các test của quy tắc mới. Không cần thay `validateScores` hay `formatReport`.

**Bài C.** `buildReport("Mai", new int[]{70,71})` trả giá trị nào?

**Đáp án:** `Mai | count=2 | avg=70 | level=PASS` vì chia nguyên `141 / 2 = 70`.

**Bài D.** Vì sao tính toán và in kết quả nên được tách? **Đáp án:** cùng phép tính có thể dùng trong CLI, web và test mà không phát sinh stdout; tầng giao diện có thể thay độc lập.

## 10. Checklist và kết luận

- [ ] Có thể mô tả trách nhiệm của mỗi phương thức bằng một câu ngắn.
- [ ] Đặt tên method phản ánh hành động hoặc kết quả thật.
- [ ] Biết đầu vào, đầu ra, điều kiện hợp lệ và lỗi có thể ném.
- [ ] Tách xác thực, tính toán, quy tắc nghiệp vụ, định dạng và hiển thị.
- [ ] Dùng một phương thức điều phối để giữ luồng xử lý dễ đọc.
- [ ] Giữ các helper nội bộ `private` khi phù hợp.
- [ ] Hạn chế thay đổi dữ liệu caller ngoài ý muốn.
- [ ] Tập trung các quy tắc lặp lại vào một nơi.
- [ ] Kiểm thử giá trị thông thường, mảng rỗng, null, chỉ số và ngưỡng.
- [ ] Không tách vụn quá mức thành hàng chục method vô nghĩa.
- [ ] Chạy `ClearMethodResponsibilitiesDemo.java` bằng JDK 17+ và so sánh exact stdout.

**Kết luận:** Tách bài toán thành các phương thức có trách nhiệm rõ ràng giúp mỗi thay đổi được **khoanh đúng phạm vi**, dễ đọc, dễ kiểm tra và dễ tái sử dụng. Hãy để hàm kiểm tra làm nhiệm vụ kiểm tra, hàm tính trả kết quả, hàm định dạng xây dựng chuỗi và tầng hiển thị chịu trách nhiệm xuất dữ liệu.