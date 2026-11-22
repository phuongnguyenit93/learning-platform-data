# Lộ trình học Java core và chương trình ví dụ xuyên suốt

Học Java dễ bị rời rạc nếu hôm nay viết một phép cộng, ngày mai học `if`, hôm sau học vòng lặp mà không thấy chúng phối hợp giải quyết vấn đề như thế nào. Một lộ trình hiệu quả nên có **đích đến cụ thể**: sau mỗi phần kiến thức, bạn bổ sung được một khả năng vào **cùng một chương trình**, tự chạy và đối chiếu kết quả.

Bài này đề xuất các chặng học nền tảng của Java core và một ví dụ xuyên suốt: **theo dõi số phút tự học mỗi ngày**. Chương trình nhận mục tiêu phút/ngày cùng thời lượng thực tế của nhiều ngày, tính tổng, trung bình và số ngày đạt mục tiêu. Đây là bài thực hành dòng lệnh, không cần framework, cơ sở dữ liệu hay kiến thức lập trình hướng đối tượng nâng cao.

## 1. Học theo khả năng làm được, không chỉ theo số bài đã đọc

| Chặng | Kiến thức cần nắm | Khả năng kiểm chứng | Phần bổ sung vào ví dụ |
| --- | --- | --- | --- |
| 1. Chạy một chương trình | JDK, tệp `.java`, `main`, `javac`, `java`, `println` | Biên dịch và in được thông điệp | In tiêu đề “Theo dõi tự học” |
| 2. Biểu diễn dữ liệu | `int`, `long`, `double`, `boolean`, `String`, biến và toán tử | Giải thích đúng kiểu và đơn vị của mỗi biến | Lưu mục tiêu, số phút, tính tổng và trung bình |
| 3. Ra quyết định | So sánh, `if`, `else`, `&&`, `||` | Dự đoán nhánh chạy ở giá trị biên | Quyết định ngày nào đạt mục tiêu |
| 4. Xử lý nhiều giá trị | `for`, mảng, chỉ số, `args` | Duyệt đúng từng phần tử, không lệch chỉ số | Tổng hợp nhiều ngày thay vì một ngày |
| 5. Tổ chức mã | Phương thức, tham số, kiểu trả về, phạm vi biến | Tách được xử lý khỏi phần nhập/xuất | Viết phương thức kiểm tra số phút hợp lệ |
| 6. Xử lý đầu vào và kiểm tra | `parseInt`, ngoại lệ, test thường và test biên | Phân biệt lỗi biên dịch, lỗi dữ liệu và lỗi logic | Từ chối số âm, chuỗi không phải số, thiếu ngày |

Đây là **trình tự gợi ý**, không phải số ngày bắt buộc phải hoàn thành. Chỉ chuyển sang chặng kế khi bạn có thể tự giải thích vì sao chương trình cho kết quả hiện tại và tự sửa một lỗi nhỏ mà không phải chép lại toàn bộ lời giải.

Không cần học generics, luồng, mạng hay framework để chạy được ví dụ đầu tiên. Những chủ đề đó có thể học khi bài toán xuất hiện nhu cầu thực sự.

## 2. Xác định yêu cầu trước khi lập trình

Giả sử bạn muốn xem mình có học đủ **60 phút mỗi ngày** trong bốn ngày gần đây không.

Đầu vào mẫu:

- Mục tiêu: `60` phút/ngày.
- Thời gian thực tế lần lượt: `45`, `60`, `20`, `80` phút.

Yêu cầu đầu ra:

| Giá trị | Kết quả tính tay |
| --- | ---: |
| Số ngày | 4 |
| Tổng phút | 45 + 60 + 20 + 80 = 205 |
| Số ngày đạt mục tiêu | 2 (ngày 2 và ngày 4) |
| Trung bình mỗi ngày | 205 / 4 = 51,25 phút |

**Quy ước của chương trình:**

- Mục tiêu phải là số nguyên **lớn hơn 0**.
- Số phút của từng ngày là số nguyên **không âm**; ngày 0 phút vẫn được tính là một ngày.
- Phải có ít nhất một ngày để tránh chia cho 0.
- Ngày có thời gian **bằng** mục tiêu được tính là đạt (`>=`).
- Mỗi đối số dòng lệnh phải biểu diễn một số nguyên trong miền `int`; giá trị `10.5` không hợp lệ ở phiên bản này.
- Trung bình có thể có phần thập phân. Chương trình in tới hai chữ số sau dấu thập phân, **không làm tròn số phút đầu vào**.

Việc nêu các quy ước trước khi code quan trọng hơn việc chọn ngay vòng lặp nào: chương trình phải đúng yêu cầu đã xác định.

## 3. Chuyển yêu cầu thành các bước xử lý

Viết thuật toán bằng lời:

1. Đọc đối số đầu tiên làm mục tiêu; những đối số tiếp theo là số phút của từng ngày.
2. Nếu thiếu mục tiêu hoặc thiếu toàn bộ dữ liệu ngày, in hướng dẫn sử dụng.
3. Chuyển văn bản thành số nguyên và từ chối dữ liệu không hợp lệ.
4. Đặt `total` (tổng phút) và `daysMet` (số ngày đạt) bằng 0.
5. Duyệt từng ngày: cộng phút vào tổng; nếu phút `>=` mục tiêu thì tăng `daysMet`.
6. Lấy tổng chia số ngày theo phép chia chấm động để tính trung bình.
7. In mục tiêu, số ngày, tổng, số ngày đạt và trung bình.

Điểm dễ nhầm là **mục tiêu không phải một ngày**. Khi xử lý mảng đối số, phần tử `args[0]` là mục tiêu, còn các ngày bắt đầu từ `args[1]`. Nếu vô tình tính cả `args[0]` như một ngày, toàn bộ thống kê sẽ sai dù chương trình vẫn biên dịch được.

## 4. Chương trình Java hoàn chỉnh

Tạo một tệp tên **`StudyTracker.java`** với nội dung sau (phù hợp JDK 17 trở lên):

~~~java
import java.util.Locale;

public class StudyTracker {
    static int parseMinutes(String raw) {
        int minutes = Integer.parseInt(raw);
        if (minutes < 0) {
            throw new IllegalArgumentException(
                    "So phut khong duoc am");
        }
        return minutes;
    }

    public static void main(String[] args) {
        if (args.length < 2) {
            System.out.println(
                    "Cach dung: java StudyTracker "
                    + "<mucTieuPhut> <ngay1> [ngay2] ...");
            return;
        }

        try {
            int goal = parseMinutes(args[0]);
            if (goal == 0) {
                throw new IllegalArgumentException(
                        "Muc tieu phai lon hon 0");
            }

            long total = 0L;
            int daysMet = 0;

            for (int i = 1; i < args.length; i++) {
                int minutes = parseMinutes(args[i]);
                total += minutes;

                if (minutes >= goal) {
                    daysMet++;
                }
            }

            int days = args.length - 1;
            double average = (double) total / days;

            System.out.println(
                    "Muc tieu: " + goal + " phut/ngay");
            System.out.println("So ngay: " + days);
            System.out.println("Tong phut: " + total);
            System.out.println(
                    "Ngay dat muc tieu: " + daysMet);
            System.out.printf(
                    Locale.ROOT,
                    "Trung binh: %.2f phut/ngay%n",
                    average);
        } catch (NumberFormatException ex) {
            System.out.println(
                    "Loi: Moi tham so phai la so nguyen hop le");
        } catch (IllegalArgumentException ex) {
            System.out.println("Loi: " + ex.getMessage());
        }
    }
}
~~~

### Giải thích theo từng chặng

**Biến và kiểu:** `goal`, `minutes`, `daysMet` là `int`; `total` là `long` để tổng nhiều ngày có miền giá trị rộng hơn mỗi số phút riêng lẻ; `average` là `double` vì trung bình có thể không nguyên. Những tên này biểu thị ý nghĩa dữ liệu thay vì chỉ là `a`, `b`, `c`.

**Điều kiện:** `if (minutes >= goal)` kiểm tra từng ngày. Ký hiệu `>=` gồm cả trường hợp bằng nhau, nên 60 phút đạt mục tiêu 60 phút.

**Vòng lặp và mảng:** `args` là `String[]`. Vòng `for` bắt đầu ở chỉ số 1, chạy khi `i < args.length`, và tăng `i` sau mỗi lượt. Java đánh chỉ số mảng từ 0.

**Phương thức:** `parseMinutes(String raw)` nhận chuỗi đầu vào, chuyển thành `int` và từ chối số âm. Việc đặt tên phương thức làm quy tắc kiểm tra có thể dùng lại cho mục tiêu và cho từng ngày.

**Ngoại lệ:** `Integer.parseInt` có thể ném `NumberFormatException` nếu chuỗi không đúng định dạng hoặc ngoài miền `int`. Đây là một lớp con của `IllegalArgumentException`, nên chương trình bắt `NumberFormatException` trước để có thông báo cụ thể.

**Phép chia:** `(double) total / days` yêu cầu phép chia chấm động. Nếu viết `total / days`, phép chia số nguyên sẽ bỏ phần lẻ **trước khi** gán vào biến `double`.

**Giới hạn:** Đây là ứng dụng nhỏ cho một lần chạy. Nó không lưu lịch sử vào tệp, không đọc thời gian hệ thống và không xác định xem người dùng đã thực sự học hay chưa; các số phút do người dùng cung cấp.

## 5. Biên dịch, chạy và đối chiếu kết quả

Mở terminal tại thư mục chứa `StudyTracker.java`. Trước hết kiểm tra công cụ:

~~~bash
java -version
javac -version
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StudyTracker.java
java StudyTracker 60 45 60 20 80
~~~

Kết quả dự kiến:

~~~text
Muc tieu: 60 phut/ngay
So ngay: 4
Tong phut: 205
Ngay dat muc tieu: 2
Trung binh: 51.25 phut/ngay
~~~

Thử truy vết bằng tay:

- `total` đi qua các giá trị 0 → 45 → 105 → 125 → 205.
- `daysMet` chỉ tăng ở số phút 60 và 80, nên kết quả là 2.
- `days = args.length - 1 = 5 - 1 = 4`.
- `average = 205.0 / 4 = 51.25`.

Chương trình này là một ví dụ **đủ nhỏ để truy vết toàn bộ** nhưng có đủ dữ liệu, điều kiện, lặp, phương thức và xử lý lỗi để thực hành nhiều chặng học.

## 6. Test các trường hợp biên

Không nên chỉ chạy dữ liệu mẫu. Hãy thử các trường hợp sau:

| Lệnh chạy | Kết quả cần kiểm tra | Kiến thức liên quan |
| --- | --- | --- |
| `java StudyTracker 60 60` | Một ngày, một ngày đạt, trung bình 60.00 | Ngưỡng bằng nhau |
| `java StudyTracker 60 0 120` | Hai ngày, một ngày đạt, trung bình 60.00 | Giá trị 0 vẫn hợp lệ |
| `java StudyTracker 60 59` | Không ngày nào đạt | Giá trị sát dưới ngưỡng |
| `java StudyTracker 60` | In hướng dẫn sử dụng | Thiếu dữ liệu ngày |
| `java StudyTracker 0 20` | Báo mục tiêu phải > 0 | Kiểm tra hợp lệ |
| `java StudyTracker -1 20` | Báo số phút không được âm | Kiểm tra đầu vào |
| `java StudyTracker 60 20 -5` | Báo lỗi số âm | Giá trị sai ở giữa dãy |
| `java StudyTracker 60 abc` | Báo chuỗi không phải số nguyên | Parse và ngoại lệ |
| `java StudyTracker 60 2.5` | Báo chuỗi không phải số nguyên | Quy ước chỉ nhận số nguyên |
| `java StudyTracker 60 2147483648` | Báo số ngoài miền `int` | Giới hạn kiểu dữ liệu |

Với dữ liệu hợp lệ, số ngày đạt luôn nằm trong khoảng từ 0 tới số ngày. Tổng phút phải không âm. Đây là các **bất biến đơn giản để tự kiểm tra kết quả**.

Lưu ý: `total` là `long` nhưng về nguyên tắc vẫn có giới hạn. Với số lượng đối số khả thi của chương trình dòng lệnh thông thường, tràn `long` khó xảy ra; nếu phát triển thành công cụ xử lý dữ liệu cực lớn, cần thêm kiểm tra tràn (ví dụ `Math.addExact`) và quy tắc lưu trữ phù hợp.

## 7. Mỗi chặng học thêm một bài tập vào cùng chương trình

Không cần viết lại một ứng dụng hoàn toàn khác sau mỗi bài học. Bạn có thể dùng cùng `StudyTracker` và nâng cấp từng bước:

| Chặng nâng cấp | Bài tập cụ thể | Dấu hiệu làm đúng |
| --- | --- | --- |
| Biến và biểu thức | In số phút còn thiếu để đạt mục tiêu của từng ngày | Không báo thiếu âm cho ngày đã đạt |
| Điều kiện | Phân loại mỗi ngày: 0 phút, dưới mục tiêu, đạt mục tiêu | Đúng các ca 0, goal−1, goal, goal+1 |
| Vòng lặp | In số thứ tự ngày cùng số phút của ngày đó | Không đưa mục tiêu vào danh sách ngày |
| Phương thức | Tạo `static boolean metGoal(int minutes, int goal)` | Từng kết quả giống với điều kiện cũ |
| Mảng | Chuyển các số phút hợp lệ vào `int[]` trước khi tổng hợp | Số phần tử bằng số ngày nhập |
| Kiểm thử | Viết một bảng input/expected output riêng | Kiểm tra cả ca thường, biên và sai |
| Nâng cao sau nền tảng | Lưu dữ liệu bằng `List` hoặc tệp, bổ sung test tự động | Không thay đổi nghĩa thống kê gốc |

Một nâng cấp nhỏ minh họa:

~~~java
static boolean metGoal(int minutes, int goal) {
    return minutes >= goal;
}
~~~

Nếu thêm phương thức này **vào trong lớp `StudyTracker`**, bạn có thể thay điều kiện `if (minutes >= goal)` trong `main` bằng `if (metGoal(minutes, goal))`. Kết quả phải giữ nguyên. Nếu thay đổi kết quả, đó là dấu hiệu refactor đã làm lệch hành vi.

Đừng làm tất cả bài tập trong một lần. Mỗi bước chỉ cần một thay đổi, biên dịch, chạy lại các trường hợp mẫu và so sánh kết quả kỳ vọng.

## 8. Cách tự học và tự kiểm tra tiến độ

Dùng một vòng học nhỏ lặp lại ở mỗi chặng:

1. **Đọc có mục đích:** nắm từ khóa, ý nghĩa và ví dụ tối thiểu.
2. **Dự đoán trước:** viết ra đầu ra kỳ vọng trước khi chạy.
3. **Tự gõ và chạy:** dùng `javac` và `java`, sửa lỗi dựa trên thông báo thật.
4. **Đổi một điều kiện:** thử giá trị biên để nhìn thấy vì sao cú pháp hay kiểu dữ liệu quan trọng.
5. **Giải thích lại:** trả lời bằng lời “vì sao dòng này ở đây?”.
6. **Ghi lại một lỗi đã gặp:** lỗi compile, lỗi runtime hay lỗi logic và cách tìm nguyên nhân.

Bạn có thể xem một chặng là đạt khi tự làm được **ba việc**: giải thích code, dự đoán đầu ra với đầu vào mới, và sửa một thay đổi nhỏ mà không làm mất hành vi đúng trước đó.

### Những bẫy học tập nên tránh

- **Chép mã nhưng không hiểu:** chạy ra đúng một lần không chứng minh bạn nắm các bước xử lý.
- **Học cú pháp tách khỏi bài toán:** đọc vòng lặp xong cần lập tức dùng nó với dữ liệu cụ thể.
- **Nâng cấp quá sớm:** không cần tạo nhiều class, database hay giao diện đồ họa để đếm phút.
- **Bỏ qua trường hợp biên:** dấu `>=` và `>` có thể chỉ khác nhau ở một giá trị nhưng thay đổi kết quả.
- **Nhầm “biên dịch được” với “đúng”:** `javac` kiểm tra cú pháp và kiểu, không tự hiểu thế nào là ngày “đạt mục tiêu”.
- **Đọc thông báo lỗi như thất bại:** lỗi là bằng chứng giúp khoanh vùng điều kiện chưa đúng.

## 9. Tự đánh giá cuối bài

Hãy trả lời mà chưa chạy lại chương trình:

**1.** Với `java StudyTracker 30 10 30 40`, tổng phút, số ngày đạt và trung bình là bao nhiêu?

*Đáp án:* Tổng 80 phút, 2 ngày đạt, trung bình `80 / 3 ≈ 26.67` phút/ngày.

**2.** Nếu vòng lặp bắt đầu từ `i = 0` thay vì `i = 1`, vấn đề gì xảy ra?

*Đáp án:* Mục tiêu bị tính nhầm thành dữ liệu của một ngày; tổng, số ngày đạt và số ngày thống kê không còn cùng ý nghĩa.

**3.** Vì sao `days` phải được tính là `args.length - 1`?

*Đáp án:* Có một đối số dùng để mô tả mục tiêu; các đối số còn lại mới là từng ngày.

**4.** Vì sao một chuỗi `"20"` có thể chuyển thành phút, còn `"hai mươi"` không được chấp nhận trong phiên bản hiện tại?

*Đáp án:* `Integer.parseInt` chỉ đọc chuỗi ở định dạng số nguyên hợp lệ theo quy tắc API, không hiểu số viết bằng chữ tiếng Việt.

**5.** Nếu muốn cho phép số phút lẻ như `45.5`, cần xem lại những gì?

*Gợi ý:* Phải thay đổi yêu cầu đầu vào, kiểu dữ liệu và cách parse, quy tắc kiểm tra, phép so sánh, hiển thị và các test. Đừng chỉ đổi `int` sang `double` mà bỏ qua cách xử lý dữ liệu đặc biệt và ý nghĩa số phút.

## Ghi nhớ

**Lộ trình học Java hiệu quả là chuỗi năng lực được kiểm chứng bằng một chương trình ngày càng hoàn thiện.** Học biến để biểu diễn dữ liệu, điều kiện để thể hiện quy tắc, vòng lặp để xử lý nhiều giá trị, phương thức để tổ chức công việc và kiểm thử để xác nhận chương trình làm đúng yêu cầu. Với `StudyTracker`, mỗi kiến thức mới đều có nơi để áp dụng và kết quả có thể tự kiểm tra — đó là cầu nối từ hiểu cú pháp đến tự giải quyết bài toán bằng Java.
