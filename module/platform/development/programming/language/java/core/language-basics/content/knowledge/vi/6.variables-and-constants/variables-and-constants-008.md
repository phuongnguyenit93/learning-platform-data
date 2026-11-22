# Hằng tại thời điểm biên dịch và hằng `static final` trong Java 17+

Trong Java, `final` có nghĩa là **biến không được gán lại sau khi đã được gán hợp lệ**, nhưng không có nghĩa mọi giá trị `final` đều được xác định lúc biên dịch.

Đặc biệt, **`static final` không tự động đồng nghĩa với “hằng tại thời điểm biên dịch”**. Một trường `static final` có thể nhận giá trị từ phép tính cố định hoặc từ một phương thức phải chạy khi lớp được khởi tạo. Hai trường hợp có ảnh hưởng khác nhau tới kiểm tra cú pháp, khởi tạo lớp và mã đã biên dịch.

## 1. Ba khái niệm cần phân biệt

| Khái niệm | Định nghĩa thực tế | Ví dụ |
| --- | --- | --- |
| Biến `final` | Biến chỉ được gán theo quy tắc của `final`, không thể gán lại sau khi đã khởi tạo | `final int count = readCount();` |
| Trường `static final` | Thuộc lớp và không thể gán lại sau khi khởi tạo; giá trị có thể tính lúc chạy | `static final int LIMIT = Integer.parseInt("12");` |
| *Constant variable* (biến hằng tại thời điểm biên dịch) | Biến `final` có kiểu nguyên thủy hoặc `String` và được khởi tạo bằng **constant expression** | `static final int LIMIT = 3 * 4;` |

Theo định nghĩa ngôn ngữ, *constant variable* **không nhất thiết phải là `static`**: `final int x = 2 + 3;` trong phương thức cũng có thể đáp ứng định nghĩa. Tuy nhiên, các hằng dùng chung của ứng dụng thường được đặt trong trường `static final`.

**Công thức ghi nhớ:**

~~~text
final + (kiểu primitive hoặc String) + constant expression
                      │
                      ▼
              constant variable

static final nhưng thiếu một điều kiện trên
                      │
                      ▼
           không phải constant variable
~~~

“Constant expression” là biểu thức mà quy tắc Java cho phép đánh giá tại thời điểm biên dịch, ví dụ literal, một số toán tử trên hằng, phép nối chuỗi hằng hoặc tham chiếu tới constant variable khác. **Gọi phương thức thông thường không phải constant expression**, ngay cả khi phương thức luôn trả cùng một số.

## 2. Ví dụ hợp lệ và không phải hằng biên dịch

~~~java
static final int MAX_USERS = 2 * 3;              // Constant variable.
static final String TITLE = "Java " + 17;        // Constant variable.
static final double RATE = 0.05;                 // Constant variable.

static final int CONFIG = Integer.parseInt("12"); // Khởi tạo lúc chạy.
static final Integer BOXED = 12;                  // Wrapper, không phải primitive/String.
static final int[] SCORES = {4, 5};               // Mảng là reference type.
static final String BUILT = new String("Java");  // Có gọi new, không phải constant expression.
~~~

Tất cả các trường trên đều `static final`. Nhưng **chỉ ba trường đầu** thỏa định nghĩa *constant variable*.

### `static final` không có nghĩa “đối tượng không thể thay đổi”

~~~java
static final int[] NUMBERS = {1, 2};

// NUMBERS = new int[]{3, 4}; // Sai: không gán lại reference final.
NUMBERS[0] = 99;              // Hợp lệ: thay phần tử mảng.
~~~

`final` ngăn gán lại **biến tham chiếu**, không đóng băng dữ liệu của đối tượng được tham chiếu. Do đó, không nên công bố mảng `public static final` rồi nghĩ rằng bên ngoài không thể sửa phần tử của nó.

Ngoài ra, trường `static final` có thể được gán trong **static initializer** đúng quy tắc, thay vì có initializer ngay tại khai báo. Trường hợp đó thường không tạo *constant variable*; một số field `final` còn có thể được xác định bằng cấu hình khi lớp được khởi tạo.

## 3. Chương trình Java 17+ chạy được: quan sát lúc khởi tạo lớp

Tạo tệp **`CompileTimeConstantsDemo.java`**:

~~~java
public class CompileTimeConstantsDemo {
    static class Settings {
        static final int MAX_USERS = 2 * 3;
        static final String LABEL = "Java " + 17;

        static final int RUNTIME_LIMIT = Integer.parseInt("12");
        static final int[] SCORES = {4, 5};

        static {
            System.out.println("Settings initialized");
        }
    }

    public static void main(String[] args) {
        final int local = 3 * 4;

        System.out.println("maxUsers=" + Settings.MAX_USERS);
        System.out.println("label=" + Settings.LABEL);
        System.out.println("local=" + local);

        System.out.println("runtimeLimit=" + Settings.RUNTIME_LIMIT);

        Settings.SCORES[0] = 90;
        System.out.println("score0=" + Settings.SCORES[0]);
    }
}
~~~

Ở PowerShell trên Windows hoặc Bash trên Linux, mở thư mục chứa tệp và chạy:

~~~bash
java -version
javac -version
javac -encoding UTF-8 CompileTimeConstantsDemo.java
java CompileTimeConstantsDemo
~~~

**Expected output:**

~~~text
maxUsers=6
label=Java 17
local=12
Settings initialized
runtimeLimit=12
score0=90
~~~

**Vì sao dòng khởi tạo lớp xuất hiện ở giữa?**

1. `MAX_USERS` và `LABEL` là *constant variables*. Khi mã truy cập bằng biểu thức `Settings.MAX_USERS` và `Settings.LABEL`, compiler có thể dùng trực tiếp giá trị hằng; **chỉ đọc chúng không buộc `Settings` khởi tạo**.
2. `local` là biến `final int` có constant expression `3 * 4`; bản thân nó không phải trường `static`.
3. `RUNTIME_LIMIT` không phải constant variable vì initializer gọi `Integer.parseInt(...)`. Lần đầu đọc field này qua `Settings.RUNTIME_LIMIT` kích hoạt khởi tạo `Settings` (nếu lớp chưa khởi tạo). Khi đó mã khởi tạo static chạy theo thứ tự, in `Settings initialized`, rồi lệnh trong `main` mới in `runtimeLimit=12`.
4. Mảng `SCORES` được tạo trong quá trình khởi tạo lớp. Dù tham chiếu là `final`, thao tác `SCORES[0] = 90` hoàn toàn hợp lệ.

Lưu ý: việc “không khởi tạo lớp khi đọc hằng” là quy tắc đối với **truy cập constant variable**, không áp dụng cho mọi cách sử dụng lớp (`new`, gọi phương thức `static` phù hợp, hoặc đọc field `static` không phải hằng có thể kích hoạt khởi tạo).

## 4. Hệ quả thực tế: hằng có thể bị nhúng vào mã gọi

Compiler có thể **nhúng trực tiếp** giá trị của *constant variable* khi biên dịch lớp sử dụng nó. Ví dụ ở một thư viện:

~~~java
public class LibraryConfig {
    public static final int LIMIT = 10;
}
~~~

Một lớp khác:

~~~java
public class Client {
    public static void main(String[] args) {
        System.out.println(LibraryConfig.LIMIT);
    }
}
~~~

Khi biên dịch `Client` dựa trên `LIMIT = 10`, mã của `Client` có thể chứa chính giá trị 10, thay vì đọc field lúc chạy. Nếu sau này thư viện sửa `LIMIT = 20` và **chỉ biên dịch lại `LibraryConfig`**, file `Client.class` cũ có thể **vẫn in 10**.

**Cách xử lý:** khi thay đổi constant variable công khai trong thư viện, **biên dịch lại các lớp sử dụng** và phát hành lại các artifact phụ thuộc. Đây là lý do không nên tùy tiện dùng `public static final` constant variables cho những giá trị dự kiến thay đổi giữa các phiên bản triển khai.

Với `static final int LIMIT = loadFromConfiguration();` (initializer gọi phương thức), giá trị không phải *compile-time constant* và việc truy cập field diễn ra lúc chạy. Nhưng nó vẫn thường chỉ được khởi tạo **một lần cho mỗi lần khởi tạo lớp**, không tự động cập nhật khi file cấu hình thay đổi.

## 5. Khi nào compiler yêu cầu constant expression?

Một tình huống dễ kiểm chứng trong Java 17 là nhãn `case` của `switch` truyền thống:

~~~java
static final int OK = 2 * 3;                // Constant variable.
static final int DYNAMIC = Math.max(5, 6); // Không phải constant variable.

// Trong phương thức:
int status = 6;
switch (status) {
    case OK:
        System.out.println("OK"); // Hợp lệ.
        break;
    // case DYNAMIC: // Sai: không phải constant expression.
    default:
        System.out.println("Khac");
}
~~~

`case OK:` được chấp nhận vì `OK` là *constant variable*, còn `DYNAMIC` không được chấp nhận ở vị trí nhãn `case` kiểu này vì lời gọi `Math.max` không phải constant expression.

Đây là lý do một giá trị được tuyên bố `final` chưa đủ để dùng trong mọi vị trí đòi hỏi **hằng lúc biên dịch**.

## 6. Lỗi và ngộ nhận thường gặp

| Ngộ nhận/tình huống | Sự thật | Cách làm |
| --- | --- | --- |
| “Có `static final` là constant variable” | Sai: initializer và kiểu còn phải thỏa điều kiện | Xét kiểu primitive/`String` và constant expression |
| “`Integer` cũng giống `int`” | `Integer` là wrapper reference type | Dùng `int` nếu cần primitive constant variable |
| “`new String("x")` là hằng vì nội dung cố định” | `new` không phải constant expression | Nếu cần hằng biên dịch, dùng `"x"` |
| “`final int[]` là mảng bất biến” | Chỉ không thể đổi tham chiếu của biến `final` | Hạn chế quyền truy cập, dùng cấu trúc bất biến phù hợp |
| “Thay `LIMIT` trong thư viện là đủ” | Lớp sử dụng đã biên dịch có thể còn giữ giá trị cũ | Rebuild và phát hành lại mã phụ thuộc |
| “Đọc mọi field `static` đều khởi tạo lớp” | Đọc constant variable là ngoại lệ đáng chú ý | Phân biệt field hằng biên dịch và field runtime |
| “`final` luôn cho phép dùng làm nhãn `case`” | Nhãn ở ví dụ cần constant expression | Dùng literal/constant variable hợp lệ |

### Quy ước đặt tên

Hằng dùng chung thường viết chữ hoa và dấu gạch dưới, ví dụ `MAX_USERS`, `DEFAULT_TIMEOUT_SECONDS`, `APP_NAME`. Đây là **quy ước**, không phải điều kiện của compiler: `static final int maxUsers = 6;` vẫn hợp lệ và vẫn có thể là constant variable.

## 7. Bài tập ngắn

**Bài 1 — Phân loại.** Đâu là *constant variable*?

~~~java
static final int A = 1 + 2;
static final int B = Integer.parseInt("3");
static final String C = "Hi" + " Java";
static final String D = new String("Hi");
static final Integer E = 3;
~~~

*Đáp án:* `A` và `C`. `B` gọi phương thức; `D` dùng `new`; `E` là wrapper.

**Bài 2 — Đọc output.** Tại sao `Settings initialized` trong ví dụ chỉ in trước `runtimeLimit=12`, không in trước `maxUsers=6`?

*Đáp án:* Hai constant variables được dùng mà không buộc lớp `Settings` khởi tạo; đọc non-constant static field `RUNTIME_LIMIT` kích hoạt khởi tạo.

**Bài 3 — Thử tính bất biến.** Với `static final int[] VALUES = {1, 2};`, câu nào hợp lệ: `VALUES[0] = 5;` hay `VALUES = new int[]{5, 6};`?

*Đáp án:* Chỉ câu thứ nhất hợp lệ: phần tử có thể sửa, biến tham chiếu `final` không thể gán lại.

**Bài 4 — Thay đổi thư viện.** Một chương trình đã biên dịch dùng `public static final int VERSION = 1;`. Tại sao thay trong thư viện thành 2 mà không rebuild client có thể vẫn in 1?

*Đáp án:* Giá trị constant variable có thể đã được nhúng vào mã client khi biên dịch.

## Checklist ghi nhớ

- [ ] Phân biệt `final`, `static final` và *constant variable*.
- [ ] Nêu đúng ba điều kiện: `final` + primitive/`String` + constant expression.
- [ ] Biết lời gọi phương thức/`new` thường khiến initializer không phải constant expression.
- [ ] Hiểu vì sao chỉ truy cập constant variable không làm lớp khai báo bắt buộc khởi tạo.
- [ ] Nhận ra `final` của tham chiếu không đồng nghĩa đối tượng bất biến.
- [ ] Biết phải biên dịch lại code phụ thuộc khi thay hằng public có thể được inline.
- [ ] Chạy được `CompileTimeConstantsDemo.java` và giải thích sáu dòng output.

**Kết luận:** `static final` thể hiện **biến cấp lớp không được gán lại**, còn *constant variable* là một trường hợp đặc biệt mà Java xác định từ **kiểu và constant expression**. Phân biệt hai khái niệm này để hiểu khởi tạo lớp, tính bất biến, `switch case` và tác động tới các file `.class` đã phát hành.
