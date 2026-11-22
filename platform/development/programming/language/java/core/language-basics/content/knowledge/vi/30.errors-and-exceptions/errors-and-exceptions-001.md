# Lỗi biên dịch, lỗi khi chạy và lỗi logic trong Java

## 1. Ba loại lỗi khác nhau ở thời điểm và cách phát hiện

Khi viết chương trình Java, không phải mọi lỗi đều được phát hiện ở cùng một giai đoạn.

| Loại | Thời điểm thường phát hiện | Dấu hiệu đặc trưng | Ví dụ |
| --- | --- | --- | --- |
| **Lỗi biên dịch** (*compile-time error*) | Khi `javac` kiểm tra mã nguồn | Biên dịch thất bại; mã nguồn vi phạm quy tắc cú pháp, tên hoặc kiểu của Java | `int x = "abc";` |
| **Lỗi khi chạy** (*runtime error/failure*) | Khi chương trình bắt đầu hoặc đang thực thi | Chương trình có thể ném ngoại lệ, gặp lỗi JVM hoặc kết thúc bất thường | Chia số nguyên cho 0, truy cập mảng vượt chỉ số |
| **Lỗi logic** (*logic error*) | Khi kiểm tra hành vi, chạy test hoặc đối chiếu yêu cầu | Chương trình có thể biên dịch và chạy không báo lỗi nhưng **kết quả sai** | Tính trung bình `a + b / 2` thay vì `(a + b) / 2.0` |

Đây là một cách **phân loại phục vụ học tập**, không có nghĩa mọi lỗi chỉ thuộc một nhóm. Chẳng hạn lỗi logic có thể dẫn tới ngoại lệ khi chạy ở một đầu vào đặc biệt; một lỗi runtime về thư viện thiếu có thể chỉ xuất hiện khi JVM cố tải lớp liên quan.

Quy trình cơ bản với một tệp Java:

```text
Mã nguồn (.java)
    |
    v
javac biên dịch và kiểm tra
    |--- Không hợp lệ ---> Lỗi biên dịch (cần sửa mã)
    |
    v
Mã bytecode (.class)
    |
    v
JVM tải lớp, khởi chạy, thực thi
    |--- Gặp ngoại lệ/lỗi ---> Thất bại khi chạy
    |
    v
Kết quả chương trình
    |--- Sai yêu cầu ----> Lỗi logic (test/đối chiếu)
    |
    v
Kết quả đáp ứng yêu cầu đã kiểm tra
```

Không có thông báo lỗi **không chứng minh** thuật toán đúng. Cần kiểm tra cả đầu ra, trạng thái dữ liệu và các trường hợp biên.

## 2. Lỗi biên dịch: `javac` không chấp nhận mã nguồn

Lỗi biên dịch xảy ra khi chương trình vi phạm các quy tắc mà trình biên dịch Java phải kiểm tra. Các nhóm thường gặp:

1. **Cú pháp:** thiếu dấu `;`, thiếu ngoặc hoặc dùng từ khóa sai vị trí.
2. **Tên và phạm vi:** gọi biến chưa khai báo, dùng biến ngoài scope, gọi phương thức không tồn tại.
3. **Kiểu dữ liệu:** gán `String` cho `int`, truyền sai kiểu đối số, trả về sai kiểu.
4. **Gán chắc chắn trước khi đọc:** biến cục bộ chưa được gán (*definite assignment*).
5. **Ngoại lệ có kiểm tra:** không bắt hoặc khai báo `throws` cho checked exception có thể phát sinh.
6. **Quy tắc lớp/tệp/quyền truy cập:** tên tệp không khớp tên kiểu top-level `public`, truy cập thành viên không được phép.

Ví dụ dưới đây là **các dòng cố tình sai; không gộp vào chương trình chạy ở mục 5**:

```java
// Sai kiểu:
int age = "18"; // incompatible types: String cannot be converted to int

// Sai tên:
System.out.println(missingValue); // cannot find symbol nếu chưa khai báo tên

// Đọc biến cục bộ chưa được gán:
int score;
System.out.println(score); // variable score might not have been initialized

// Sai cú pháp:
// int count = 5 // thiếu dấu chấm phẩy
```

Cách sửa tùy ý định:

```java
int age = 18; // Dùng literal int

int missingValue = 7;
System.out.println(missingValue);

int score = 0;
System.out.println(score);
```

Các đoạn trên minh họa trong thân phương thức, không phải tệp chạy độc lập. Lưu ý: `Integer.parseInt("18")` là một cách chuyển chuỗi thành số nếu dữ liệu thật là văn bản, nhưng nếu nội dung không phải số hợp lệ thì phương thức có thể ném `NumberFormatException` **khi chạy**. Việc chuyển chuỗi sang số vì thế đòi hỏi quy tắc kiểm tra dữ liệu.

### Trường hợp checked exception

Nếu gọi API khai báo checked exception, trình biên dịch buộc mã xử lý ngoại lệ hoặc khai báo để chuyển trách nhiệm cho bên gọi:

```java
import java.nio.file.Files;
import java.nio.file.Path;

class FileExample {
    static String readText() throws java.io.IOException {
        return Files.readString(Path.of("missing.txt"));
    }
}
```

`throws java.io.IOException` khiến ví dụ **biên dịch hợp lệ**. Tuy vậy, nếu tệp không tồn tại, lời gọi `Files.readString` vẫn có thể ném `NoSuchFileException` khi chương trình chạy. **Trình biên dịch kiểm tra cách xử lý ngoại lệ, không bảo đảm môi trường runtime có đủ tệp hoặc mạng hoạt động.**

### Cách đọc lỗi biên dịch

Chạy `javac -encoding UTF-8 Example.java` rồi đọc chẩn đoán trên luồng lỗi (stderr). Thông tin thường gồm tên tệp, số dòng, vị trí và diễn giải như `cannot find symbol`, `incompatible types` hoặc `';' expected`. Nội dung chẩn đoán có thể khác theo phiên bản JDK, nên không nên coi mọi thông báo lỗi biên dịch là chuỗi stdout cố định. Sửa **lỗi đầu tiên có ý nghĩa** rồi biên dịch lại: một dấu ngoặc hoặc khai báo sai có thể dẫn đến nhiều lỗi phụ ở những dòng sau.

## 3. Lỗi khi chạy: chương trình biên dịch được nhưng không thực thi như mong đợi

Nhiều lỗi chỉ xuất hiện khi JVM gặp một **giá trị cụ thể** hoặc **điều kiện môi trường cụ thể**.

| Tình huống | Hành vi Java thường gặp |
| --- | --- |
| `12 / 0` với phép chia nguyên | `ArithmeticException` khi thực thi phép chia |
| Đọc `arr[arr.length]` | `ArrayIndexOutOfBoundsException` |
| Gọi phương thức qua tham chiếu `null` | `NullPointerException` |
| `Integer.parseInt("abc")` | `NumberFormatException` |
| Mở tệp không tồn tại | Thường là `NoSuchFileException` khi dùng `Files.readString` |
| Ép một đối tượng sang kiểu tham chiếu không tương thích | `ClassCastException` |
| Hết bộ nhớ có thể cấp phát | Có thể ném `OutOfMemoryError` |

**Ngoại lệ** (*exception*) là đối tượng mô tả một tình trạng bất thường trong lúc thực thi; nhiều ngoại lệ là các kiểu con của `Exception` hoặc `RuntimeException`. Các lỗi nghiêm trọng hơn của JVM thường được biểu diễn bởi các kiểu con của `Error`, ví dụ `OutOfMemoryError`. Cả hai nhánh này đều thuộc `Throwable`, nhưng **không nên bắt `Error` để tiếp tục hoạt động bình thường** như thể đó là dữ liệu đầu vào sai đơn giản.

Phân biệt **checked exception** và **unchecked exception**:

- `IOException` là checked exception: trình biên dịch thường yêu cầu `try/catch` hoặc `throws`.
- `ArithmeticException`, `NullPointerException`, `NumberFormatException` là unchecked exceptions thuộc `RuntimeException`: không phải khai báo `throws` mới biên dịch được, nhưng vẫn có thể phát sinh khi chạy.
- `Error` và các lớp con cũng là unchecked theo cơ chế kiểm tra ngoại lệ, nhưng thường biểu diễn tình huống nặng hơn và không phải loại lỗi nghiệp vụ để xử lý bằng `catch` thông thường.

Một số thất bại lúc khởi chạy không nhất thiết là lỗi ném ra từ thân `main`. Ví dụ gọi `java MissingClass` trong khi không có lớp phù hợp trên classpath có thể khiến trình khởi chạy báo không tìm thấy hoặc không tải được lớp chính. Khi chẩn đoán phải phân biệt vấn đề **biên dịch mã** với **cấu hình classpath/module path lúc chạy**.

### Khi ngoại lệ không được bắt

Khi một exception không được xử lý ở đường gọi hiện tại, nó lan ngược qua các lời gọi. Nếu đi đến luồng thực thi mà không được xử lý, JVM thường ghi thông tin ngoại lệ và **stack trace** lên stderr. Stack trace giúp xác định kiểu ngoại lệ, nơi ném và chuỗi phương thức gọi. Đừng nuốt ngoại lệ bằng khối `catch` rỗng: việc đó có thể che mất nguyên nhân.

Việc dùng `try/catch` **không sửa sai logic**; nó chỉ xác định cách xử lý một tình huống bất thường. Ví dụ truy cập sai chỉ số nên sửa điều kiện vòng lặp, không dùng `catch (ArrayIndexOutOfBoundsException)` để che lỗi lập trình.

## 4. Lỗi logic: mã hợp lệ, chạy được nhưng cho đáp án sai

Đây thường là loại lỗi khó thấy nhất vì chương trình có thể kết thúc bình thường.

### Sai thứ tự ưu tiên toán tử

```java
int a = 8;
int b = 4;
int wrong = a + b / 2;         // 10 do phép chia làm trước
double correct = (a + b) / 2.0; // 6.0
```

`wrong` có giá trị `10`, không phải trung bình `6`. Lỗi không phát sinh ngoại lệ và cũng không bị `javac` từ chối.

### Chia nguyên làm mất phần thập phân

```java
int total = 5;
int count = 2;
double wrong = total / count;   // 2.0: phép chia int thực hiện trước
double correct = total / 2.0;   // 2.5: phép chia kiểu double
```

Dù biến đích là `double`, phép `total / count` vẫn là phép chia nguyên khi hai toán hạng đều có kiểu `int`. Nếu muốn phần lẻ, cần làm cho ít nhất một toán hạng mang kiểu số thực thích hợp.

### Điều kiện biên và điều kiện sai

```java
int[] values = {10, 20, 30};
int sum = 0;
for (int i = 0; i < values.length - 1; i++) {
    sum += values[i];
}
// sum == 30, trong khi tổng đủ ba phần tử phải là 60.
```

Vòng lặp trên chạy hợp lệ nhưng bỏ sót phần tử cuối. Một điều kiện khác `i <= values.length` có thể dẫn tới **runtime exception** vì cố truy cập phần tử ở chỉ số `values.length` (không hợp lệ).

Với `boolean`, câu lệnh `if (enabled = true)` có thể **biên dịch hợp lệ** vì phép gán trả về giá trị `boolean`, nhưng vừa sửa trạng thái `enabled` vừa làm điều kiện thành `true`. Muốn kiểm tra giá trị, dùng `if (enabled)` hoặc phép so sánh phù hợp.

Lỗi logic còn có thể đến từ hiểu nhầm yêu cầu (ví dụ “ít nhất 18 tuổi” lại dùng `age > 18`), sai đơn vị đo, tràn số nguyên, sắp xếp sai chiều hoặc giả định dữ liệu luôn không rỗng.

## 5. Chương trình Java 17+ độc lập để quan sát hai nhóm lỗi khi chạy và lỗi logic

Tạo một tệp **`ErrorKindsDemo.java`**:

```java
public class ErrorKindsDemo {
    static int wrongAverage(int a, int b) {
        return a + b / 2; // Sai logic: không đặt ngoặc
    }

    static double correctAverage(int a, int b) {
        return (a + b) / 2.0;
    }

    public static void main(String[] args) {
        int a = 8;
        int b = 4;

        int wrong = wrongAverage(a, b);
        double correct = correctAverage(a, b);
        System.out.println("Trung binh sai: " + wrong);
        System.out.println("Trung binh dung: " + correct);

        int divisor = 0;
        try {
            int quotient = 12 / divisor;
            System.out.println(quotient);
        } catch (ArithmeticException ex) {
            System.out.println("Loi chia: " + ex.getClass().getSimpleName());
        }

        int[] values = {3, 5};
        try {
            System.out.println(values[2]);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("Loi chi so: " + ex.getClass().getSimpleName());
        }

        try {
            int parsed = Integer.parseInt("abc");
            System.out.println(parsed);
        } catch (NumberFormatException ex) {
            System.out.println("Loi chuyen so: " + ex.getClass().getSimpleName());
        }

        int total = 5;
        int count = 2;
        System.out.println("Chia nguyen sai: " + (double) (total / count));
        System.out.println("Chia thuc dung: " + (total / (double) count));

        System.out.println("Chuong trinh tiep tuc.");
    }
}
```

Mở terminal trong thư mục chứa file, dùng **JDK 17 trở lên**. Trên Windows PowerShell/CMD hoặc Linux/macOS:

```bash
javac -encoding UTF-8 ErrorKindsDemo.java
java ErrorKindsDemo
```

**Stdout chính xác** (biên dịch thành công không in thông báo):

```text
Trung binh sai: 10
Trung binh dung: 6.0
Loi chia: ArithmeticException
Loi chi so: ArrayIndexOutOfBoundsException
Loi chuyen so: NumberFormatException
Chia nguyen sai: 2.0
Chia thuc dung: 2.5
Chuong trinh tiep tuc.
```

Đoạn này **cố ý không đưa mã có lỗi biên dịch vào file**, để chương trình có thể chạy độc lập. Ba ngoại lệ ở giữa được bắt ngay trong `main` nên không in stack trace mặc định, và chương trình tiếp tục. Nếu bỏ một khối `catch`, ngoại lệ tương ứng có thể làm đường thực thi `main` kết thúc sớm. Hai phép tính trung bình và chia nguyên minh họa lỗi logic, vì JVM không thể tự biết kết quả nghiệp vụ nào là đúng.

Không nên đánh giá mã này là “không có lỗi” chỉ vì stdout xuất hiện bình thường: mục đích ví dụ là quan sát sự khác nhau giữa **kết quả sai im lặng** và **ngoại lệ khi chạy đã được bắt**.

## 6. Quy trình xác định và xử lý lỗi

### Bước 1 — Xác định giai đoạn

- **`javac` thất bại:** tập trung lỗi cú pháp, tên, kiểu, quyền truy cập, biến chưa khởi tạo hoặc checked exception chưa xử lý.
- **Biên dịch được nhưng chạy báo lỗi/ngoại lệ:** đọc stack trace, dòng lỗi, điều kiện đầu vào và trạng thái môi trường.
- **Chạy xong nhưng output sai:** tái hiện đầu vào, tính tay kết quả mong đợi và kiểm tra các bước thuật toán.

### Bước 2 — Thu nhỏ ví dụ

Tách đoạn gây lỗi thành chương trình nhỏ nhất có thể tái hiện vấn đề. Dùng các giá trị đầu vào đơn giản và kết quả dễ kiểm tra. Trong Java, thêm `System.out.println` để quan sát trạng thái khi học, hoặc dùng debugger của IDE để đặt breakpoint, xem biến và đi từng dòng.

### Bước 3 — Kiểm thử cả biên và trường hợp bất thường

Các trường hợp nên thử phụ thuộc bài toán: `0`, số âm, mảng rỗng, mảng một phần tử, `null`, chuỗi không hợp lệ, giá trị rất lớn, tài nguyên không tồn tại. Với phương thức tính trung bình, nên kiểm tra `(8,4)`, `(5,2)`, hai số âm và các giá trị có thể gây tràn khi cộng nếu dùng `int`.

### Bước 4 — Viết test có kết quả kỳ vọng cụ thể

Ví dụ, một phép kiểm thử thủ công trong `main`:

```java
double actual = (8 + 4) / 2.0;
double expected = 6.0;
if (Double.compare(actual, expected) != 0) {
    throw new AssertionError("Average mismatch");
}
```

Nếu phép tính bị đổi thành `8 + 4 / 2.0`, điều kiện sẽ phát hiện kết quả `10.0` không khớp `6.0`. Với tính toán số thực tổng quát, thường nên so sánh theo **dung sai** phù hợp thay vì chỉ so sánh `double` tuyệt đối bằng nhau; ví dụ số học đơn giản này cho kết quả biểu diễn chính xác.

Có thể tổ chức test bằng JUnit trong dự án thật. Test không thể chứng minh tuyệt đối không còn lỗi với mọi đầu vào, nhưng giúp phát hiện hồi quy khi sửa mã.

### Bước 5 — Sửa nguyên nhân, không chỉ che triệu chứng

Nếu vòng lặp bỏ sót phần tử, sửa điều kiện; nếu dữ liệu có thể `null`, quyết định có cho phép `null` hay cần kiểm tra/khước từ; nếu chia cho 0, xác định yêu cầu xử lý mẫu số 0. Tránh `catch (Exception ex) { }` rỗng hoặc trả giá trị mặc định tùy tiện, vì làm lỗi khó chẩn đoán hơn.

## 7. Công cụ và thông báo nên biết

| Công cụ/cách làm | Mục đích |
| --- | --- |
| `javac -encoding UTF-8 File.java` | Biên dịch file Java đúng mã hóa nguồn |
| `javac -Xlint:all File.java` | Bật thêm các cảnh báo biên dịch được hỗ trợ |
| `java ClassName` | Thực thi lớp có phương thức `main` phù hợp |
| Breakpoint và debugger | Xem giá trị biến, stack và các bước thực thi |
| Stack trace | Xác định vị trí và chuỗi lời gọi dẫn đến ngoại lệ |
| Unit test | Kiểm tra đầu ra/trạng thái với dữ liệu kỳ vọng |
| Log có ngữ cảnh | Ghi lại thông tin hữu ích mà không che lỗi |

**Cảnh báo biên dịch không giống lỗi biên dịch**: mặc định nhiều cảnh báo vẫn cho phép sinh `.class`. Cũng không thể khẳng định `javac -Xlint:all` sẽ tìm ra mọi lỗi logic. Phân biệt stdout (kết quả chương trình) với stderr (thường chứa chẩn đoán), và lưu ý thông điệp ngoại lệ có thể khác theo phiên bản JDK hoặc môi trường.

## 8. Tổng kết bằng ba câu hỏi

1. **Chưa biên dịch được?** Xem lỗi compile-time và sửa mã theo cú pháp/quy tắc kiểu của Java.
2. **Biên dịch được nhưng khi chạy thất bại?** Xem exception, stack trace, dữ liệu đầu vào, phụ thuộc và môi trường.
3. **Chạy bình thường nhưng kết quả sai?** Xem logic, đặc tả, thứ tự toán tử, vòng lặp, trường hợp biên và kiểm thử.

**Ghi nhớ:** lỗi biên dịch bị chặn trước khi thực thi; lỗi khi chạy xuất hiện trong quá trình khởi chạy/thực thi; lỗi logic có thể im lặng dù chương trình hoàn tất. Một chương trình chất lượng cần **biên dịch đúng, chạy ổn định và đáp ứng kết quả mong đợi**.