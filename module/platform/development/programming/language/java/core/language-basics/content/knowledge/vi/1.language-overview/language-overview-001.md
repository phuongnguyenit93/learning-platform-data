# Ngôn ngữ Java là gì và dùng để diễn đạt bài toán như thế nào?

Khi mới học lập trình, nhiều người thấy chương trình chỉ là những dòng chữ có dấu `;`, dấu `{}` và từ khóa khó nhớ. Cách nhìn hữu ích hơn là: **Java là một ngôn ngữ để biến quy tắc giải quyết một bài toán thành các chỉ dẫn mà máy tính có thể kiểm tra và thực thi**. Ta cần hiểu bài toán trước, sau đó chọn dữ liệu, đặt tên, mô tả điều kiện và tính toán bằng Java.

Bài này dành cho người mới học Java core. Bạn sẽ xây dựng và chạy một chương trình nhỏ mà không cần thư viện ngoài hay framework.

## 1. Sau bài học, bạn làm được gì?

- Phân biệt **ngôn ngữ Java**, tệp mã nguồn `.java`, trình biên dịch `javac`, tệp bytecode `.class` và JVM.
- Chuyển một yêu cầu bằng tiếng Việt thành **đầu vào → quy tắc xử lý → đầu ra** có thể kiểm chứng.
- Nhận diện vai trò của biến, kiểu dữ liệu, biểu thức, điều kiện, phương thức và lời gọi trong một chương trình Java đơn giản.
- Tạo một lớp Java có `main`, biên dịch bằng `javac` và chạy bằng `java`.
- Thử các giá trị thường gặp, giá trị biên và dữ liệu sai; phân biệt lỗi cú pháp, lỗi khi chạy và lỗi logic.
- Hiểu giới hạn của một chương trình minh họa: quy tắc nghiệp vụ phải do bài toán xác định, Java không tự suy ra điều người dùng muốn.

## 2. Java là gì?

**Java** là một ngôn ngữ lập trình có cú pháp và quy tắc kiểu dữ liệu. Với Java, ta có thể viết ứng dụng dòng lệnh, hệ thống máy chủ, công cụ xử lý dữ liệu, ứng dụng doanh nghiệp và nhiều chương trình khác. Java còn là tên thường được dùng để nói về hệ sinh thái công cụ, thư viện và môi trường chạy liên quan.

Ví dụ, hai dòng sau đang **diễn đạt một ý định** bằng cú pháp Java:

~~~java
int numberOfBooks = 3;
System.out.println(numberOfBooks * 25_000);
~~~

Đọc bằng tiếng Việt: “Có 3 cuốn sách, mỗi cuốn giá 25.000 đồng; in tổng tiền.” Kết quả là `75000`. Máy không hiểu “cuốn sách” theo nghĩa đời thực; máy thao tác với **số 3**, **số 25.000** và phép nhân theo quy tắc ta viết.

Java không phải JavaScript. Tên giống nhau nhưng đó là hai ngôn ngữ khác nhau với hệ thống kiểu, cú pháp và môi trường thực thi khác nhau.

### Mã nguồn được chạy như thế nào?

~~~mermaid
flowchart LR
    A["Bài toán và quy tắc"] --> B["ShippingQuote.java<br/>mã nguồn"]
    B --> C["javac<br/>kiểm tra và biên dịch"]
    C --> D["ShippingQuote.class<br/>bytecode"]
    D --> E["JVM chạy chương trình"]
    E --> F["Kết quả hoặc lỗi khi chạy"]
~~~

- **`.java`:** tệp văn bản chứa mã nguồn mà người lập trình viết.
- **`javac`:** trình biên dịch Java trong JDK; phát hiện nhiều lỗi cú pháp và kiểu dữ liệu, sau đó tạo bytecode nếu biên dịch thành công.
- **`.class`:** tệp chứa bytecode cho JVM; không phải bản văn mã nguồn.
- **JVM (Java Virtual Machine):** môi trường thực thi bytecode. JVM còn kiểm tra và thực hiện nhiều hoạt động lúc chạy.
- **JDK (Java Development Kit):** bộ công cụ phát triển, gồm `javac`, công cụ `java` và các thành phần cần thiết để xây dựng/chạy ứng dụng.

Trên máy khác, mã đã biên dịch có thể chạy với JVM tương thích nếu phiên bản Java và các phụ thuộc phù hợp. Vì vậy, “viết một lần, chạy mọi nơi” là **mục tiêu khả chuyển**, không có nghĩa mọi chương trình Java đều chạy trên mọi máy mà không cần cấu hình.

## 3. Từ đề bài tiếng Việt đến mô hình xử lý

Giả sử cửa hàng giao hàng đặt ra **quy tắc minh họa** (không phải bảng giá của một đơn vị vận chuyển thật):

> Tính tổng số tiền khách phải trả. Nếu khách là thành viên hoặc giá trị đơn hàng từ **500.000 VND trở lên**, miễn phí giao. Nếu không, phí giao cơ bản **15.000 VND** cho tối đa 5 km; từ km thứ 6, cộng **2.000 VND** cho mỗi km vượt quá 5 km.

Chúng ta chưa nên mở trình soạn thảo và viết `if` ngay. Trước hết hãy xác định hợp đồng của bài toán.

| Thành phần | Tên trong Java | Ý nghĩa/giới hạn |
| --- | --- | --- |
| Đầu vào 1 | `orderValueVnd`: `long` | Tiền hàng, tính bằng **VND nguyên**, không âm |
| Đầu vào 2 | `distanceKm`: `int` | Số kilomet nguyên không âm |
| Đầu vào 3 | `member`: `boolean` | Khách có phải thành viên hay không |
| Trung gian | `shippingVnd`: `long` | Phí giao tính từ ba đầu vào |
| Đầu ra | `totalVnd`: `long` | Tiền hàng + phí giao |
| Lỗi dữ liệu | `IllegalArgumentException` | Ví dụ giá tiền hoặc quãng đường âm |

Cần công bố thêm những giả định để tránh hiểu sai:

- Khoảng cách được làm tròn/ghi nhận **theo số km nguyên** trước khi truyền vào chương trình; bài này chưa giải quyết số km thập phân.
- “Từ 500.000 trở lên” bao gồm **đúng 500.000**, nên dùng `>=`, không dùng `>`.
- Miễn phí giao chỉ thay đổi `shippingVnd`, không thay đổi giá trị hàng.
- Phép tính không bao gồm giảm giá, thuế, COD hay chi phí khác vì đề bài không yêu cầu.
- Dữ liệu sai phải được báo lỗi thay vì âm thầm đổi thành 0.

Những lựa chọn trên là **quy tắc nghiệp vụ**. Java chỉ cung cấp cách biểu diễn chúng chính xác.

### Viết thuật toán bằng lời trước khi viết Java

1. Nhận giá trị đơn, số km và trạng thái thành viên.
2. Từ chối giá trị đơn âm hoặc số km âm.
3. Nếu là thành viên **hoặc** giá trị đơn từ 500.000, phí giao bằng 0.
4. Nếu không, phí giao bằng 15.000 cộng 2.000 cho mỗi km vượt quá 5.
5. Lấy giá trị đơn cộng phí giao và in cả hai thành phần cùng tổng.

Chính chuỗi bước này mới là “lời giải”. Java giúp biến lời giải thành các câu lệnh có thể thực thi, thay vì tự nghĩ ra thuật toán cho chúng ta.

## 4. Java biểu đạt từng phần của bài toán bằng gì?

| Ý trong bài toán | Công cụ Java | Ví dụ ngắn |
| --- | --- | --- |
| Lưu một giá trị | Biến và kiểu | `long orderValueVnd = 300_000L;` |
| Biểu diễn có/không | `boolean` | `boolean member = false;` |
| Tính toán | Biểu thức | `15_000L + 3L * 2_000L` |
| So sánh với ngưỡng | Toán tử so sánh | `orderValueVnd >= 500_000L` |
| Kết hợp các điều kiện | Toán tử logic | `member || orderValueVnd >= 500_000L` |
| Chọn nhánh | `if` / `else` hoặc `return` sớm | Miễn phí hay tính phí |
| Đặt tên cho một khả năng | Phương thức | `calculateShipping(...)` |
| Nhận dữ liệu từ lệnh chạy | Tham số `String[] args` | `args[0]` chứa văn bản đầu tiên |
| Hiển thị kết quả | `System.out.println(...)` | In ra tổng tiền |

Dấu gạch dưới trong số như `300_000L` chỉ để dễ đọc: giá trị vẫn là ba trăm nghìn. Hậu tố `L` chỉ literal kiểu `long`. Phép `||` mang nghĩa **HOẶC**, chỉ cần một điều kiện đúng thì toàn biểu thức đúng.

Bạn không phải thuộc lòng mọi cú pháp trước khi hiểu bài toán; hãy liên hệ mỗi câu lệnh với **một điều cần làm** trong yêu cầu.

## 5. Chương trình Java hoàn chỉnh, có thể biên dịch và chạy

Tạo tệp tên chính xác **`ShippingQuote.java`** và chép toàn bộ mã sau. Ví dụ tương thích với JDK 17 trở lên, đồng thời không cần tính năng đặc thù Java 17.

~~~java
import java.util.Locale;

public class ShippingQuote {
    private static final long FREE_AT_VND = 500_000L;
    private static final long BASE_FEE_VND = 15_000L;
    private static final long EXTRA_KM_FEE_VND = 2_000L;

    static long calculateShipping(
            long orderValueVnd, int distanceKm, boolean member) {

        if (orderValueVnd < 0) {
            throw new IllegalArgumentException(
                    "Gia tri don khong duoc am");
        }
        if (distanceKm < 0) {
            throw new IllegalArgumentException(
                    "Khoang cach khong duoc am");
        }

        if (member || orderValueVnd >= FREE_AT_VND) {
            return 0L;
        }

        long extraKm = Math.max(0L, (long) distanceKm - 5L);
        long extraFee = Math.multiplyExact(
                extraKm, EXTRA_KM_FEE_VND);
        return Math.addExact(BASE_FEE_VND, extraFee);
    }

    public static void main(String[] args) {
        if (args.length != 3) {
            System.out.println(
                    "Cach dung: java ShippingQuote "
                    + "<tienHangVnd> <khoangCachKm> <true|false>");
            return;
        }

        try {
            long orderValueVnd = Long.parseLong(args[0]);
            int distanceKm = Integer.parseInt(args[1]);

            String memberText = args[2].toLowerCase(Locale.ROOT);
            if (!memberText.equals("true")
                    && !memberText.equals("false")) {
                throw new IllegalArgumentException(
                        "Thanh vien phai la true hoac false");
            }
            boolean member = Boolean.parseBoolean(memberText);

            long shippingVnd = calculateShipping(
                    orderValueVnd, distanceKm, member);
            long totalVnd = Math.addExact(
                    orderValueVnd, shippingVnd);

            System.out.println(
                    "Tien hang: " + orderValueVnd + " VND");
            System.out.println(
                    "Phi giao: " + shippingVnd + " VND");
            System.out.println(
                    "Tong cong: " + totalVnd + " VND");
        } catch (NumberFormatException ex) {
            System.out.println(
                    "Loi dinh dang so: " + ex.getMessage());
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Loi du lieu: " + ex.getMessage());
        } catch (ArithmeticException ex) {
            System.out.println("Loi tran so: " + ex.getMessage());
        }
    }
}
~~~

**Giải thích các khối chính:**

- `public class ShippingQuote` định nghĩa lớp chứa chương trình. Với lớp `public` này, tên tệp phải là `ShippingQuote.java`.
- `main(String[] args)` là điểm bắt đầu thông thường khi chạy lớp bằng lệnh `java ShippingQuote ...`. Các đối số sau tên lớp đi vào mảng `args` dưới dạng **chuỗi**, chưa phải số.
- `Long.parseLong(...)` và `Integer.parseInt(...)` biến chuỗi có định dạng số hợp lệ thành giá trị số tương ứng; dữ liệu sai gây `NumberFormatException`.
- `calculateShipping` là một **phương thức** đặt tên cho thao tác tính phí. Đầu vào và giá trị trả về được khai báo ngay tại chữ ký; phương thức không tự đọc bàn phím hay in kết quả.
- `if` kiểm tra quy tắc, `return 0L` kết thúc phương thức sớm khi đủ điều kiện miễn phí.
- `Math.max(0L, (long) distanceKm - 5L)` cho số km **vượt quá 5**, không tạo số âm; ép sang `long` trước phép trừ giúp phép tính dùng kiểu đủ rộng.
- `Math.multiplyExact` và `Math.addExact` tính toán số nguyên và ném `ArithmeticException` nếu phép toán bị tràn trong kiểu `long`. Đây là cách kiểm soát rủi ro khi mở rộng bài toán.
- Ba nhánh `catch` báo ba nhóm lỗi khác nhau. `NumberFormatException` là một loại `IllegalArgumentException` nên phải bắt nhánh cụ thể trước nhánh tổng quát; `ArithmeticException` là loại ngoại lệ khác.

Đây là **một lớp Java thực thi được**, không cần tạo thêm `package` hoặc cài thêm thư viện ngoài JDK.

## 6. Biên dịch, chạy và đọc kết quả

Mở terminal tại đúng thư mục chứa `ShippingQuote.java`. Kiểm tra JDK:

~~~bash
java -version
javac -version
~~~

Tiếp theo:

~~~bash
javac -encoding UTF-8 ShippingQuote.java
java ShippingQuote 300000 8 false
~~~

Kết quả:

~~~text
Tien hang: 300000 VND
Phi giao: 21000 VND
Tong cong: 321000 VND
~~~

Vì sao phí giao là 21.000?

1. `member = false` và `300000 < 500000` nên **không** được miễn phí.
2. Khoảng cách 8 km vượt mức cơ bản 5 km đúng **3 km**.
3. Phí cộng thêm: `3 * 2000 = 6000`.
4. Phí giao: `15000 + 6000 = 21000`.
5. Tổng cộng: `300000 + 21000 = 321000`.

Thử tiếp giá trị **đúng ngưỡng**:

~~~bash
java ShippingQuote 500000 8 false
~~~

~~~text
Tien hang: 500000 VND
Phi giao: 0 VND
Tong cong: 500000 VND
~~~

Và khách **thành viên**:

~~~bash
java ShippingQuote 120000 8 true
~~~

~~~text
Tien hang: 120000 VND
Phi giao: 0 VND
Tong cong: 120000 VND
~~~

Cách chạy này là **chương trình dòng lệnh**. Thông tin nhập qua `args` do người dùng truyền lúc chạy, khác với việc đọc tương tác từng dòng từ bàn phím. Khi chỉ muốn học cấu trúc ngôn ngữ, chọn input qua tham số làm ví dụ gọn và dễ lặp lại.

## 7. Đọc một dòng Java theo nghĩa của nó

Xét:

~~~java
long extraKm = Math.max(0L, (long) distanceKm - 5L);
~~~

Ta có thể đọc từ phải sang trái:

1. `distanceKm` đang là số nguyên `int`.
2. `(long) distanceKm` chuyển giá trị sang kiểu `long`.
3. Trừ 5 để biết phần khoảng cách vượt ngưỡng.
4. `Math.max(0L, ...)` lấy giá trị lớn hơn, tránh phần vượt là số âm.
5. Gán kết quả cho biến có tên `extraKm` và kiểu `long`.
6. Dấu `;` kết thúc câu lệnh khai báo/gán giá trị này.

Đây là minh họa cho **biểu thức** (phần được tính thành một giá trị) nằm trong **câu lệnh** (một hành động của chương trình).

Ví dụ khác:

~~~java
if (member || orderValueVnd >= FREE_AT_VND) {
    return 0L;
}
~~~

- `if` hỏi điều kiện có đúng không.
- `()` chứa điều kiện.
- `||` ghép hai điều kiện. Java đánh giá ngắn mạch: nếu `member` đã đúng, không cần đánh giá vế sau.
- `{}` nhóm các câu lệnh thuộc nhánh.
- `return` trả lại kết quả và kết thúc lời gọi phương thức đó.

**Dấu `=` là phép gán, còn `==` là phép so sánh bằng nhau** (với kiểu phù hợp). Nhầm hai khái niệm này có thể gây lỗi biên dịch hoặc lỗi logic.

## 8. Kiểu dữ liệu phải phù hợp với ý nghĩa bài toán

Trong Java, kiểu dữ liệu không chỉ là phần trang trí bên cạnh tên biến. Kiểu quyết định dạng giá trị được lưu và những phép toán hợp lệ.

| Kiểu | Thể hiện điều gì trong bài này? | Điều cần tránh |
| --- | --- | --- |
| `int` | Quãng đường km nguyên, trong miền hợp lệ của `int` | Chuyển một chuỗi quá lớn thành `int` |
| `long` | Giá trị tiền VND nguyên và tổng tiền | Tính vượt giới hạn `long` |
| `boolean` | Có/không là thành viên | Hiểu một chuỗi bất kỳ là giá trị `true` |
| `String` | Các tham số dạng văn bản trong `args` | Mang chuỗi vào phép cộng số mà chưa chuyển kiểu |

Tiền có đơn vị **VND nguyên** nên dùng kiểu số nguyên. `double` là số chấm động hữu ích trong nhiều phép tính khoa học, nhưng không nên mặc nhiên dùng nó để biểu diễn tiền chính xác đến đơn vị nhỏ nhất vì biểu diễn nhị phân có thể gây sai số. Với tiền có phần thập phân hoặc quy tắc làm tròn phức tạp, có thể cần `BigDecimal` và quy tắc đơn vị/làm tròn riêng.

Cũng đừng dùng tên biến mơ hồ như `x`, `a`, `n` cho mọi thứ. `orderValueVnd` và `shippingVnd` dài hơn nhưng cho thấy cả **ý nghĩa** lẫn **đơn vị**, giảm khả năng cộng nhầm tiền với kilomet.

## 9. Trường hợp biên và lỗi cần nghĩ đến

Một chương trình chạy đúng với ví dụ 300.000 VND chưa đủ chứng minh thuật toán đúng. Hãy dùng các ca sau làm **bảng kiểm thử bằng tay**:

| Input: tiền, km, thành viên | Phí giao kỳ vọng | Lý do |
| --- | ---: | --- |
| `300000 0 false` | 15.000 | Chưa vượt 5 km |
| `300000 5 false` | 15.000 | Chính xác điểm kết thúc giá cơ bản |
| `300000 6 false` | 17.000 | Vượt 1 km |
| `300000 8 false` | 21.000 | Vượt 3 km |
| `499999 8 false` | 21.000 | Ngay dưới ngưỡng miễn phí |
| `500000 8 false` | 0 | Đúng ngưỡng miễn phí |
| `120000 8 true` | 0 | Thành viên |
| `0 8 false` | 21.000 | Tiền hàng bằng 0 vẫn hợp lệ theo giả định |
| `-1 8 false` | Không tính, báo lỗi | Tiền âm |
| `300000 -1 false` | Không tính, báo lỗi | Khoảng cách âm |
| `abc 8 false` | Không tính, báo lỗi | Không chuyển thành `long` được |
| `300000 8 yes` | Không tính, báo lỗi | Không thuộc `true/false` |
| `300000 8` | In hướng dẫn sử dụng | Thiếu đối số |

Một lỗi điển hình là viết `orderValueVnd > 500_000L` thay vì `>=`. Hầu hết các ví dụ khác vẫn qua, nhưng **đúng 500.000** sẽ bị tính phí sai. Đây là lỗi logic: chương trình có thể biên dịch và chạy, nhưng **kết quả trái yêu cầu**.

### Ba nhóm vấn đề khác nhau

**Lỗi biên dịch:** Viết sai cú pháp, tên biến hoặc kiểu không tương thích. Ví dụ:

~~~java
// Sai: thiếu dấu ; ở cuối câu lệnh.
long fee = 15_000L
~~~

`javac` báo lỗi và không tạo chương trình hợp lệ để chạy.

**Lỗi lúc chạy:** Mã đã biên dịch, nhưng đầu vào hoặc trạng thái gây ngoại lệ. Ví dụ, `Long.parseLong("abc")` ném `NumberFormatException`; chương trình có thể bắt và báo cho người dùng.

**Lỗi logic:** Mã biên dịch, chạy bình thường nhưng làm sai quy tắc. Ví dụ `distanceKm >= 5` tính phụ phí ngay tại km thứ 5 nếu thuật toán viết sai. Vì vậy, test phải dựa vào **đề bài**, không chỉ dựa vào việc “máy không báo lỗi”.

Các trường hợp như giá trị số quá lớn, thiếu tham số hoặc chuỗi `TRUE` cũng cần được quyết định bằng hợp đồng. Ví dụ này chấp nhận `TRUE` vì chủ động chuyển chữ thường trước khi kiểm tra.

## 10. Vì sao nên tách phương thức xử lý khỏi `main`?

`main` chịu trách nhiệm nhận và chuyển đổi **đầu vào của chương trình**, gọi xử lý và in kết quả. `calculateShipping` chịu trách nhiệm **quy tắc tính phí**.

Sự phân chia giúp:

- Đọc nhanh một hàm và biết nó trả về gì.
- Thử tính phí với nhiều tham số mà không phải giả lập terminal.
- Thay đổi cách lấy đầu vào (dòng lệnh, giao diện, API) mà không viết lại toàn bộ quy tắc.
- Tránh rải số `500_000`, `15_000` và `2_000` khắp nơi nhờ đặt thành hằng số có tên.

Không cần tạo nhiều lớp hay framework chỉ để tính phí vận chuyển. Đối với ví dụ nhỏ, **một lớp và một phương thức rõ ràng** là đủ.

Có thể tự kiểm tra vài lời gọi trong một chương trình thử nghiệm:

~~~java
System.out.println(ShippingQuote.calculateShipping(300_000, 8, false)); // 21000
System.out.println(ShippingQuote.calculateShipping(500_000, 8, false)); // 0
System.out.println(ShippingQuote.calculateShipping(300_000, 5, false)); // 15000
~~~

Ba câu lệnh trên chỉ là **đoạn minh họa đặt bên trong một phương thức** ở cùng thư mục/package mặc định; không phải một tệp Java độc lập. Một bước học tiếp theo là biến các kỳ vọng này thành kiểm thử tự động.

## 11. Những điều ngôn ngữ Java không tự làm thay bạn

Java có trình biên dịch kiểm tra nhiều quy tắc, nhưng **không tự biết đúng sai nghiệp vụ**.

Ví dụ:

- `javac` có thể kiểm tra `calculateShipping` trả về giá trị `long` theo các đường điều khiển hợp lệ.
- Nó không thể kết luận “phí cơ bản phải là 15.000” trừ khi bạn diễn đạt điều ấy trong mã và kiểm thử đối chiếu yêu cầu.
- Nó không tự quyết định nên thu phí theo số km thực, số km làm tròn hay vùng giao hàng.
- Nó không tự bảo đảm dữ liệu từ người dùng, cơ sở dữ liệu hoặc mạng luôn có giá trị hợp lệ.
- Một chương trình Java có thể chạy trên nhiều nền tảng phù hợp, nhưng đường dẫn, kết nối mạng, encoding và thư viện ngoài vẫn có thể ảnh hưởng khi triển khai.

**Chương trình đúng** cần cả hai: ngôn ngữ thực thi đúng mã được viết và **mã đó diễn đạt đúng bài toán**.

## 12. Tự luyện tập: biến một yêu cầu mới thành mã

**Bài 1 — Dự đoán trước khi chạy.** Giữ nguyên chương trình, chạy `java ShippingQuote 499999 5 false`. Phí giao và tổng cộng phải là bao nhiêu?

*Đáp án kiểm tra:* phí giao `15000`, tổng `514999`.

**Bài 2 — Đổi quy tắc.** Cửa hàng đổi ngưỡng miễn phí từ 500.000 lên 600.000 VND. Hãy chỉ ra dòng cần đổi, rồi thử cả `599999` và `600000` với khách không là thành viên.

*Gợi ý:* đổi `FREE_AT_VND` rồi kiểm tra phía dưới và đúng ngưỡng. Đừng sửa kết quả dự đoán trước khi đọc lại yêu cầu.

**Bài 3 — Truy vết.** Với `orderValueVnd = 200_000`, `distanceKm = 10` và `member = false`, đi lần lượt qua `if`, `extraKm`, `extraFee`, `shippingVnd` và `totalVnd`.

*Đáp án:* `extraKm = 5`, `extraFee = 10000`, `shippingVnd = 25000`, `totalVnd = 225000`.

**Bài 4 — Tìm lỗi logic.** Một bạn viết:

~~~java
long extraKm = Math.max(0L, (long) distanceKm - 4L);
~~~

Điều gì xảy ra với đơn không được miễn phí giao ở 5 km? Tại sao sai so với đặc tả?

*Đáp án:* sẽ thu thêm 2.000 VND ngay ở km thứ 5; đề bài nói chỉ thu thêm từ km thứ 6.

**Bài 5 — Tự thiết kế bài toán mới.** Viết bảng **đầu vào / đầu ra / giả định / quy tắc / trường hợp biên** cho một vấn đề nhỏ như đổi phút sang giờ, tính tiền vé theo độ tuổi hoặc tìm số lớn nhất trong ba số. Sau đó viết giả mã bằng tiếng Việt trước khi chuyển sang Java.

**Tiêu chí hoàn thành:** Bạn giải thích được một yêu cầu đời thực, ánh xạ từng thành phần sang dữ liệu và câu lệnh Java, biên dịch/chạy được chương trình, và tự chỉ ra ít nhất ba trường hợp khiến kết quả có thể sai nếu quy tắc viết thiếu chính xác.

## Ghi nhớ

Java là **ngôn ngữ diễn đạt thuật toán và quy tắc** theo một cú pháp có thể biên dịch, kiểm tra kiểu và thực thi trên JVM. Để dùng Java giải bài toán, hãy đi từ **yêu cầu rõ → dữ liệu và đơn vị rõ → điều kiện/tính toán rõ → mã chạy được → kiểm thử cả đầu vào thường và biên**. Khi biết mỗi biến, câu lệnh và phương thức đang đại diện cho điều gì trong bài toán, việc học các cấu trúc Java ở mức chi tiết hơn sẽ có ý nghĩa hơn việc chỉ ghi nhớ từ khóa.
