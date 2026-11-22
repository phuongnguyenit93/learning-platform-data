# Từ đầu vào tới xử lý và đầu ra của một chương trình Java

> **Java core — language-basics / Tổng quan**  
> **Mục tiêu:** Sau bài này, bạn giải thích được đường đi **Input → Processing → Output (IPO)**, biết chương trình Java nhận dữ liệu ở đâu, kiểm tra và biến đổi thế nào, in kết quả hoặc báo lỗi ra sao. Bạn cũng có thể tự biên dịch/chạy một ứng dụng console đơn giản, thử dữ liệu bình thường và các trường hợp biên.

## 1. Một chương trình làm gì với dữ liệu?

Hãy tưởng tượng người dùng muốn tính tiền mua bút. Họ nhập tên món hàng, đơn giá và số lượng. Chương trình kiểm tra dữ liệu, tính thành tiền, rồi hiển thị kết quả.

| Giai đoạn | Câu hỏi cần trả lời | Ví dụ mua hàng |
| --- | --- | --- |
| **Input — Đầu vào** | Dữ liệu được lấy từ đâu? Hình dạng ban đầu là gì? | Bàn phím cung cấp `"Bút bi"`, `"12000"`, `"3"` dưới dạng những dòng ký tự |
| **Processing — Xử lý** | Dữ liệu có hợp lệ không? Cần tính hay quyết định điều gì? | Chuyển giá thành `long`, số lượng thành `int`, kiểm tra giá không âm, số lượng dương; tính `12000 × 3` |
| **Output — Đầu ra** | Kết quả hoặc lỗi được gửi tới đâu? | In `Tổng tiền: 36000 VND` hoặc lý do đầu vào không hợp lệ |

Đừng nhầm **đầu vào** với “dữ liệu đã được xử lý”. Người dùng gõ `12000` trên bàn phím; chương trình trước tiên nhận được **chuỗi ký tự** `"12000"`, sau đó mới chuyển sang số `12000L`. Việc nhập thành công **không** đồng nghĩa dữ liệu hợp lệ.

~~~mermaid
flowchart TD
    A["Người dùng / nguồn dữ liệu"] --> B["Đọc input: dòng ký tự"]
    B --> C["Phân tích cú pháp + kiểm tra"]
    C --> D{"Hợp lệ?"}
    D -->|Không| E["Thông báo lỗi qua stderr"]
    D -->|Có| F["Xử lý nghiệp vụ: tính toán"]
    F --> G{"Phép toán hợp lệ?"}
    G -->|Không| E
    G -->|Có| H["In kết quả qua stdout"]
~~~

Quy trình IPO không chỉ áp dụng cho console. Với một ứng dụng web, đầu vào có thể là HTTP request, xử lý là kiểm tra và tính toán, đầu ra là HTTP response. Với ứng dụng đọc tệp, đầu vào là nội dung tệp và đầu ra có thể là tệp kết quả. **Ba bước tư duy không thay đổi**, còn cách kết nối nguồn/đích thì khác.

## 2. Đầu vào trong Java: dữ liệu đến từ đâu?

Một chương trình Java thông thường có nhiều nguồn đầu vào:

| Nguồn | Java API/cách dùng điển hình | Khi nào phù hợp? |
| --- | --- | --- |
| **Đối số dòng lệnh** | Mảng `String[] args` trong `main` | Tham số được truyền **khi khởi động** chương trình |
| **Bàn phím/standard input** | `System.in`, thường được bọc bằng `Scanner` hoặc `BufferedReader` | Hội thoại nhập liệu tại terminal; nhận dữ liệu đã chuyển hướng từ tệp/pipe |
| **Tệp** | `Files.readString`, `Files.newBufferedReader`, v.v. | Đọc dữ liệu đã được lưu |
| **Lời gọi từ chương trình khác** | Tham số phương thức, object, API/network | Dữ liệu đến từ các thành phần khác của hệ thống |

Ví dụ với đối số dòng lệnh:

~~~java
public class ArgumentsDemo {
    public static void main(String[] args) {
        System.out.println("So doi so: " + args.length);
        if (args.length > 0) {
            System.out.println("Doi so dau: " + args[0]);
        }
    }
}
~~~

Biên dịch và chạy (Java 11+):

~~~bash
javac ArgumentsDemo.java
java ArgumentsDemo xin-chao
~~~

Kết quả:

~~~text
So doi so: 1
Doi so dau: xin-chao
~~~

Nếu chạy `java ArgumentsDemo`, `args.length` bằng `0`. Cố truy cập `args[0]` khi mảng rỗng sẽ gây `ArrayIndexOutOfBoundsException`; vì vậy mã trên kiểm tra độ dài trước.

**Phân biệt:** `args` là dữ liệu đã truyền vào lúc khởi động. `System.in` là luồng để đọc **trong thời gian chương trình đang chạy**; cả hai đều có thể cung cấp chuỗi nhưng vòng đời và cách sử dụng khác nhau.

## 3. Standard input, standard output và standard error

Một ứng dụng console thường dùng ba luồng chuẩn:

| Luồng | Trong Java | Mục đích |
| --- | --- | --- |
| **stdin** (*standard input*) | `System.in` | Nhận các byte đầu vào, thường từ terminal |
| **stdout** (*standard output*) | `System.out` | In kết quả thông thường |
| **stderr** (*standard error*) | `System.err` | In thông báo lỗi/chẩn đoán |

Ví dụ:

~~~java
System.out.println("Tong tien: 36000 VND");
System.err.println("Loi: so luong phai lon hon 0");
~~~

Tại terminal, **cả hai dòng có thể cùng xuất hiện trên màn hình**, nên rất dễ tưởng stdout và stderr là một. Nhưng khi chuyển hướng luồng, chúng có thể được xử lý riêng. Điều này hữu ích khi một chương trình được tự động hóa: chương trình khác có thể đọc kết quả từ stdout mà không nhầm với lời báo lỗi.

`System.in` là luồng **byte**. Khi cần đọc văn bản, Java thường bọc nó trong một `InputStreamReader` để giải mã byte thành ký tự, rồi `BufferedReader` để đọc từng dòng:

~~~java
BufferedReader input = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
String line = input.readLine();
~~~

Cần import `java.io.BufferedReader`, `java.io.InputStreamReader` và `java.nio.charset.StandardCharsets`. `readLine()` trả một `String`, bỏ ký tự kết thúc dòng; **trả `null` khi đã hết dữ liệu**, chứ không trả một chuỗi rỗng. Đây là khác biệt quan trọng khi đầu vào đến từ tệp hoặc pipe.

`Scanner` là lựa chọn đơn giản cho nhiều bài học nhập số, nhưng `Scanner.nextInt()` phụ thuộc cách tách token và locale, dễ phát sinh bất ngờ khi dùng xen kẽ `nextInt()` với `nextLine()`. Ví dụ chính của bài dùng `BufferedReader.readLine()`, sau đó chủ động chuyển kiểu và kiểm tra để thấy rõ từng bước IPO.

## 4. Một chương trình chạy được từ đầu đến cuối

Bài toán: người dùng nhập **tên một mặt hàng**, **đơn giá VND** và **số lượng**. Chương trình tính tổng tiền của đúng mặt hàng đó.

**Hợp đồng đầu vào:**

- Tên món hàng không được trống hoặc chỉ chứa khoảng trắng.
- Đơn giá là **số nguyên từ 0 tới `Long.MAX_VALUE`**; giá 0 được phép, ví dụ hàng tặng.
- Số lượng là **số nguyên dương từ 1 tới `Integer.MAX_VALUE`**.
- Tổng tiền `đơn giá × số lượng` phải nằm trong phạm vi `long`.
- Chương trình đọc chính xác **ba dòng** từ stdin theo đúng thứ tự.
- Khi hợp lệ, chương trình in tên hàng và tổng tiền ra stdout. Khi lỗi, in thông báo ra stderr và thoát bằng trạng thái khác 0.

Ví dụ chọn `long` cho tiền nguyên VND, thay vì `float`/`double` để tránh sai số nhị phân trong ví dụ tiền tệ. Một phần mềm tài chính thực có thể dùng `BigDecimal` và cần quy định tiền tệ/đơn vị/làm tròn chi tiết hơn; bài này chỉ minh họa luồng xử lý và một hợp đồng số nguyên rõ ràng.

### 4.1. Mã nguồn: PurchaseFlowDemo.java

Tạo tệp **PurchaseFlowDemo.java** và chép toàn bộ mã sau. Chương trình dùng Java 11 trở lên, không cần thư viện ngoài JDK.

~~~java
import java.io.BufferedReader;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class PurchaseFlowDemo {

    // Sau khi kiểm tra, chương trình giữ giá trị đã có đúng kiểu.
    static final class Purchase {
        final String productName;
        final long unitPriceVnd;
        final int quantity;

        Purchase(String productName, long unitPriceVnd, int quantity) {
            this.productName = productName;
            this.unitPriceVnd = unitPriceVnd;
            this.quantity = quantity;
        }
    }

    // INPUT: đọc đúng một dòng văn bản, không giả định luôn có dữ liệu.
    private static String requestLine(
            BufferedReader reader, String prompt) throws IOException {

        System.out.print(prompt);
        System.out.flush();

        String line = reader.readLine();
        if (line == null) {
            throw new EOFException("Thieu du lieu tai: " + prompt);
        }
        return line.strip();
    }

    // INPUT + VALIDATION: đổi String thành kiểu dữ liệu phù hợp.
    private static Purchase readPurchase(
            BufferedReader reader) throws IOException {

        String name = requestLine(reader, "Ten san pham: ");
        String rawPrice = requestLine(reader, "Don gia (VND): ");
        String rawQuantity = requestLine(reader, "So luong: ");

        if (name.isEmpty()) {
            throw new IllegalArgumentException("Ten san pham khong duoc rong");
        }

        long price;
        int quantity;
        try {
            price = Long.parseLong(rawPrice);
            quantity = Integer.parseInt(rawQuantity);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                    "Don gia va so luong phai la so nguyen hop le", error);
        }

        if (price < 0) {
            throw new IllegalArgumentException("Don gia khong duoc am");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("So luong phai lon hon 0");
        }
        return new Purchase(name, price, quantity);
    }

    // PROCESSING: chỉ tính toán, không đọc từ bàn phím hay in ra màn hình.
    private static long calculateTotal(Purchase purchase) {
        return Math.multiplyExact(
                purchase.unitPriceVnd, (long) purchase.quantity);
    }

    // OUTPUT: trình bày kết quả đã xử lý.
    private static void printReceipt(Purchase purchase, long total) {
        System.out.println("Mat hang : " + purchase.productName);
        System.out.println("Tong tien: " + total + " VND");
    }

    public static void main(String[] args) {
        BufferedReader reader = new BufferedReader(
                new InputStreamReader(System.in, StandardCharsets.UTF_8));

        try {
            Purchase purchase = readPurchase(reader);
            long total = calculateTotal(purchase);
            printReceipt(purchase, total);
        } catch (EOFException error) {
            System.err.println("Loi dau vao: " + error.getMessage());
            System.exit(1);
        } catch (IllegalArgumentException | ArithmeticException error) {
            System.err.println("Loi du lieu/tinh toan: " + error.getMessage());
            System.exit(1);
        } catch (IOException error) {
            System.err.println("Loi doc stdin: " + error.getMessage());
            System.exit(1);
        }
    }
}
~~~

Có bốn nhóm trách nhiệm dễ nhìn thấy:

| Phương thức | Giai đoạn | Điều nó làm | Điều nó **không** làm |
| --- | --- | --- | --- |
| `requestLine` | Input | Nhắc nhập, đọc một dòng, phát hiện hết dữ liệu | Không nhân giá và số lượng |
| `readPurchase` | Input / Validation | Gom ba dòng, chuyển sang `long`/`int`, từ chối đầu vào sai | Không in hóa đơn |
| `calculateTotal` | Processing | Tính tổng với kiểm tra tràn số | Không tự đọc từ `System.in` |
| `printReceipt` | Output | Định dạng và in kết quả hợp lệ | Không tự sửa quy tắc tính tiền |

Cách tách này giúp thấy **dòng dữ liệu** thay vì chỉ nhìn một khối code có lẫn đọc, tính, in. Với chương trình nhỏ hơn, bạn hoàn toàn có thể viết tất cả vào `main`; việc tách method ở đây phục vụ mục đích giáo dục, **không phải quy tắc buộc mọi chương trình phải có bốn phương thức**.

### 4.2. Biên dịch bằng javac, chạy bằng java

Mở terminal tại thư mục chứa tệp `PurchaseFlowDemo.java`:

~~~bash
javac -encoding UTF-8 PurchaseFlowDemo.java
java PurchaseFlowDemo
~~~

Khi chương trình hỏi, lần lượt nhập:

~~~text
Ten san pham: But bi
Don gia (VND): 12000
So luong: 3
Mat hang : But bi
Tong tien: 36000 VND
~~~

Ba dòng bắt đầu bằng lời nhắc là **phần tương tác khi bạn gõ và nhấn Enter**; hai dòng `Mat hang` và `Tong tien` là kết quả được chương trình in. Compiler tạo `PurchaseFlowDemo.class`, còn lệnh `java PurchaseFlowDemo` khởi động lớp đã biên dịch. **Không** thêm đuôi `.class` khi truyền tên lớp cho `java`.

Thử nhập `0` cho đơn giá và `5` cho số lượng, kết quả sẽ là `0 VND`. Thử nhập khoảng trắng đầu/cuối tên món hàng: `strip()` cắt khoảng trắng hai đầu. Cách hiển thị ký tự có dấu tại terminal phụ thuộc cấu hình mã hóa/console; trong mã có khai báo UTF-8 cho **đầu vào**.

## 5. Dữ liệu chảy qua chương trình như thế nào?

Với đầu vào:

~~~text
But bi
12000
3
~~~

Bảng sau mô phỏng từng trạng thái:

| Bước | Giá trị trong chương trình | Kiểu dữ liệu | Ý nghĩa |
| --- | --- | --- | --- |
| Đọc tên | `"But bi"` | `String` | Chưa kiểm tra tên rỗng |
| Đọc giá | `"12000"` | `String` | Vẫn là văn bản |
| Đọc số lượng | `"3"` | `String` | Vẫn là văn bản |
| Chuyển và kiểm tra giá | `12000L` | `long` | Số nguyên không âm |
| Chuyển và kiểm tra lượng | `3` | `int` | Số nguyên dương |
| Tính toán | `36000L` | `long` | `12000 × 3` |
| In kết quả | `"Tong tien: 36000 VND"` | Chuỗi xuất ra stdout | Người dùng thấy kết quả |

Dữ liệu được **chuyển từ biểu diễn bên ngoài** (chuỗi) thành **giá trị Java có kiểu**, sau đó được kiểm tra theo quy tắc nghiệp vụ. Không có bước xử lý hợp lệ nếu số lượng là `"ba"`: gọi `Integer.parseInt("ba")` sẽ ném `NumberFormatException`; trong ví dụ, lỗi được biến thành một thông báo dễ hiểu hơn cho người dùng.

Phân biệt hai kiểu câu hỏi:

- **Hợp lệ về cú pháp?** `"1000"` parse được thành số; `"1,000"` hoặc `"1 000"` không parse trực tiếp bằng `Long.parseLong`.
- **Hợp lệ về nghiệp vụ?** `"-100"` parse được thành số, nhưng **giá âm** bị từ chối; `"0"` parse được thành số, nhưng **số lượng 0** không hợp lệ theo hợp đồng.

Mã tính tiền dùng `Math.multiplyExact` thay cho phép nhân thông thường để **không trả một số đã tràn** nếu giá × lượng vượt phạm vi `long`.

## 6. Edge cases: đầu vào hỏng và cách chương trình phản hồi

| Dữ liệu nhập | Điều xảy ra | Vì sao? |
| --- | --- | --- |
| Tên là chuỗi rỗng hoặc toàn khoảng trắng | In lỗi tên rỗng | `strip()` và `isEmpty()` phát hiện tên không có nội dung |
| Giá là `-1` | In lỗi giá âm | Parse thành công nhưng sai nghiệp vụ |
| Giá là `0`, số lượng là `2` | In tổng `0 VND` | Giá 0 được phép theo hợp đồng |
| Số lượng là `0` | In lỗi số lượng không dương | Quy tắc yêu cầu ít nhất một món |
| Số lượng là `2.5` hoặc `hai` | In lỗi số nguyên | `Integer.parseInt` không nhận số thực/chữ |
| Giá là `1_000` | In lỗi số nguyên | Dấu gạch dưới hợp lệ trong **literal source Java**, không phải cú pháp mà `parseLong` nhận từ người dùng |
| Giá vượt `Long.MAX_VALUE` | In lỗi số nguyên | Số không biểu diễn được bằng `long` |
| Giá = `Long.MAX_VALUE`, lượng = `2` | In lỗi tính toán | `Math.multiplyExact` phát hiện tràn `long` |
| Chỉ đưa hai dòng rồi kết thúc stdin | In lỗi thiếu dữ liệu | `readLine()` trả `null` tại EOF |
| Có dòng trống giữa hai giá trị | Dòng trống được đọc như input thật | `readLine()` không tự bỏ qua dòng trống |
| Có thêm dòng thứ tư | Chương trình bỏ qua dòng thứ tư | Hợp đồng ví dụ chỉ đọc ba dòng |

Một lỗi không có nghĩa là “chương trình in tổng tiền bằng 0”. **Không nên tự chuyển input sai thành 0 để code khỏi báo lỗi**, vì khi đó người dùng không phân biệt được dữ liệu sai với giá trị hợp lệ. Chương trình dừng với mã trạng thái 1 và ghi lỗi lên stderr, thay vì tạo một hóa đơn trông có vẻ thành công.

Một điểm nhỏ nhưng có ý nghĩa: ở ví dụ này, `readPurchase` **đọc hết ba dòng rồi mới kiểm tra tên**. Nếu tên rỗng, người dùng vẫn được hỏi giá và số lượng trước khi thấy thông báo lỗi. Đó là lựa chọn thứ tự xử lý của ví dụ, **không** phải hành vi mặc định Java. Bạn có thể cải thiện UX bằng kiểm tra ngay sau khi đọc từng trường, nhưng hãy nhận biết sự khác biệt về thứ tự lời nhắc.

## 7. Thử tự động và chuyển hướng luồng

Vì chương trình đọc từ **stdin**, bạn không bắt buộc phải gõ tay. Trong shell có hỗ trợ pipe, một chương trình khác có thể cấp dữ liệu cho nó.

**macOS/Linux — terminal shell:**

~~~bash
printf 'But bi\n12000\n3\n' | java PurchaseFlowDemo
~~~

**Windows PowerShell:**

~~~powershell
@('But bi', '12000', '3') | java PurchaseFlowDemo
~~~

Đầu ra có cùng kết quả tính tiền; khi stdin được pipe từ lệnh khác, các lời nhắc có thể hiện liền nhau vì bản thân dữ liệu nhập **không nhất thiết được terminal echo lại**. Đừng so nguyên hình thức lời nhắc tương tác với transcript gõ tay.

Để nhận biết stderr khác stdout (ví dụ trên macOS/Linux hoặc shell hỗ trợ cú pháp tương đương):

~~~bash
printf 'But bi\n12000\n0\n' | java PurchaseFlowDemo > result.txt 2> errors.txt
~~~

- `> result.txt` chuyển **stdout** sang tệp `result.txt`.
- `2> errors.txt` chuyển **stderr** sang `errors.txt`.
- Trong trường hợp sai số lượng, `errors.txt` có thông báo lỗi; `result.txt` có thể chứa các lời nhắc nhập mà chương trình đã in trước khi lỗi.
- Mã thoát khác 0 báo chương trình không hoàn tất thành công. Cách kiểm tra mã thoát khác nhau giữa shell, ví dụ `echo $?` trong Bash sau lệnh.

**Chú ý:** Lệnh chuyển hướng trên tác động tới luồng của **tiến trình**; `System.out` và `System.err` vẫn là các API Java. Java không cần biết dữ liệu đang đến từ bàn phím, tệp hay pipe để đọc từng dòng bằng `BufferedReader`.

## 8. Gỡ lỗi bằng cách đi ngược dòng dữ liệu

Khi kết quả không đúng, lần theo đúng từng bước:

1. **Có nhận được input không?** `readLine()` trả `null` hay chuỗi? Có đang chờ Enter không?
2. **Chuỗi đọc được là gì?** Có khoảng trắng đầu/cuối, dòng rỗng, dấu phân cách lạ không? Tránh in mật khẩu/thông tin nhạy cảm khi debug.
3. **Phân tích cú pháp ra sao?** `parseInt/parseLong` chấp nhận chuỗi đó không? Kiểu số có đủ phạm vi không?
4. **Đã kiểm tra nghiệp vụ chưa?** Giá âm, số lượng bằng 0 hoặc vượt ngưỡng hợp lệ có bị chặn không?
5. **Phép tính có an toàn không?** Có phép cộng/nhân vượt `int`/`long` không? Nếu cần, dùng các phương thức `Math.*Exact` tương ứng.
6. **Đã xuất kết quả nào?** Đầu ra thành công có chỉ xuất khi mọi bước trước hợp lệ không? Thông báo lỗi có đi vào stderr không?

Một số lỗi hay gặp:

| Triệu chứng | Khả năng | Cách xem xét |
| --- | --- | --- |
| Chương trình “đứng yên” sau lời nhắc | Đang chờ dữ liệu từ stdin | Nhập một dòng và Enter hoặc cung cấp đủ input qua pipe |
| `NumberFormatException` | Chuỗi không phải số nguyên được hỗ trợ | Kiểm tra ký tự lạ, dấu phẩy, số quá lớn |
| `NullPointerException` khi gọi method trên `readLine()` | Không xử lý EOF trước | Kiểm tra `null` như `requestLine` |
| Giá đúng nhưng tổng âm bất thường | Tràn kiểu số với phép nhân thường | Dùng `Math.multiplyExact` và xử lý lỗi |
| Máy hiển thị chữ tiếng Việt sai dấu | Mã hóa console không khớp | Kiểm tra terminal, charset nguồn/input/output |
| Không tìm được main class | Sai thư mục chạy/classpath/tên lớp | Kiểm tra biên dịch thành công, chạy `java PurchaseFlowDemo` |

Đừng mặc định mọi lỗi nhập liệu đều là `IOException`: chuyển số sai thường gây `NumberFormatException` (một `IllegalArgumentException`), còn đọc nguồn lỗi thật mới là trường hợp `IOException`. Việc phân biệt giúp thông báo lỗi và cách khắc phục chính xác hơn.

## 9. Từ ví dụ console đến thiết kế dễ kiểm thử

Đầu vào/đầu ra phụ thuộc **môi trường**; phần tính toán có thể viết như một hàm thuần. Đây là lý do ta tách:

~~~java
private static long calculateTotal(Purchase purchase) {
    return Math.multiplyExact(
            purchase.unitPriceVnd, (long) purchase.quantity);
}
~~~

Nếu đơn giá là `12000` và số lượng là `3`, hàm cho kết quả `36000` mà không cần bàn phím. Nếu đơn giá là `Long.MAX_VALUE` và lượng là `2`, hàm ném `ArithmeticException` mà không in kết quả. Hai hành vi đó có thể kiểm tra trực tiếp bằng unit test khi nâng cấp dự án.

Trong chương trình thực, nguồn vào có thể đổi từ terminal sang HTTP request hoặc file CSV. Nếu phần xử lý không tự đọc input và không tự in output, ta có thể **tái sử dụng quy tắc** mà không phải mang theo phụ thuộc vào console. Tuy vậy, tách lớp và kiến trúc sâu hơn không phải mục tiêu bắt buộc của bài nhập môn: trước tiên hãy nắm cách dữ liệu đi qua từng giai đoạn.

### Kiểm thử thủ công theo hợp đồng

Hãy thử ít nhất các trường hợp sau, ghi lại input/kỳ vọng trước khi chạy:

| Trường hợp | Input ba dòng | Kỳ vọng |
| --- | --- | --- |
| Bình thường | `But bi / 12000 / 3` | `Tong tien: 36000 VND` |
| Hàng miễn phí | `Qua tang / 0 / 2` | `Tong tien: 0 VND` |
| Tên trống | `(trống) / 12000 / 3` | Thông báo tên không được rỗng |
| Số lượng sai | `But bi / 12000 / 0` | Thông báo lượng phải dương |
| Không phải số | `But bi / abc / 3` | Thông báo yêu cầu số nguyên |
| Tràn số | `But bi / 9223372036854775807 / 2` | Lỗi tràn, không có dòng tổng tiền |

Một bộ test hữu ích luôn có **ca bình thường + ca biên + ca lỗi**, không chỉ có một ảnh chụp màn hình chứng minh chương trình in được một phép nhân.

## 10. Bài tập thực hành

**Bài 1 — Vẽ luồng IPO:** Với ứng dụng tính điểm trung bình từ ba bài kiểm tra, hãy xác định đầu vào, kiểu dữ liệu nội bộ, công thức xử lý, cách hiển thị kết quả và những dữ liệu không hợp lệ. Nếu điểm hợp lệ là `0..10`, bạn kiểm tra ở giai đoạn nào?

**Bài 2 — Thêm giảm giá:** Thêm một dòng đầu vào “Phần trăm giảm giá” (số nguyên `0..100`) rồi tính tiền cuối. Chỉ rõ thứ tự nhân/chia và cách làm tròn bằng phép tính số nguyên. Viết trước các ca 0%, 100%, 50% và input ngoài phạm vi. Đây là **mở rộng tính năng** chứ không còn là bản gốc ba dòng.

**Bài 3 — Cải thiện thông báo nhập lỗi:** Trong `readPurchase`, kiểm tra tên ngay sau khi đọc và giá ngay sau khi parse; để input sai được báo sớm. Quan sát thay đổi về số lời nhắc nhưng vẫn giữ công thức thành tiền.

**Bài 4 — Phân biệt stdout/stderr:** Cấp số lượng 0 bằng pipe, chuyển hướng hai luồng ra hai tệp. Dòng nào là kết quả, dòng nào là lỗi? Vì sao một công cụ tự động nên dựa cả vào mã thoát?

**Bài 5 — Đổi nguồn input:** Thay bàn phím bằng dữ liệu từ một tệp văn bản có ba dòng. Dùng `<` của shell nơi hỗ trợ hoặc `Files.newBufferedReader`. Chỉ ra phần nào của chương trình phải thay, phần nào có thể giữ nguyên.

### Tự đánh giá

Bạn hiểu bài khi có thể: **(1)** mô tả đường đi Input → Validation → Processing → Output; **(2)** phân biệt `String` đọc vào với giá trị số đã parse; **(3)** chỉ rõ vai trò `System.in`, `System.out`, `System.err`; **(4)** giải thích vì sao dữ liệu sai hoặc tràn số **không được in như kết quả thành công**; và **(5)** tự chạy/chẩn đoán ví dụ bằng `javac`/`java`.
