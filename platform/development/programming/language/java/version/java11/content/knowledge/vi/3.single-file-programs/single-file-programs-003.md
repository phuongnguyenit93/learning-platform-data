# Truyền tham số cho chương trình một tệp (Java 11)

Trong Java 11, bạn có thể chạy trực tiếp một tệp nguồn bằng lệnh `java TenTep.java`. **Đối số đặt sau tên tệp** được chuyển vào mảng `String[] args` của phương thức `main`, giống như khi chạy một lớp Java đã biên dịch. Tính năng này vẫn hữu ích trên các JDK hiện nay cho bài học, thử nghiệm nhanh và tiện ích nhỏ.

Bài học chỉ sử dụng cú pháp và API đã có ở **Java 11** và vẫn áp dụng hiện nay. Có thể dùng **JDK 25 LTS đang được cập nhật** để chạy ví dụ, với `--source 11` nếu muốn giữ rõ ranh giới kiến thức Java 11. Nếu dùng JDK khác, xác nhận nó còn được nhà cung cấp hỗ trợ và còn chấp nhận mức nguồn 11.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Chạy một chương trình nguồn Java trực tiếp, không cần gõ lệnh `javac` riêng.
2. Xác định **đối số nào được truyền cho chương trình** và **tùy chọn nào dành cho JVM/Java launcher**.
3. Đọc, đếm và truy cập `args` theo chỉ số; hiểu rằng mọi đối số ban đầu đều là chuỗi.
4. Dùng dấu nháy để truyền chuỗi có khoảng trắng, số và cờ dạng `--option`.
5. Kiểm tra đủ số lượng đối số, chuyển đổi kiểu số an toàn, báo lỗi rõ ràng và dùng mã thoát thích hợp.
6. Nhận biết giới hạn của chương trình một tệp và cách áp dụng cách truyền tham số vào dự án thật.

## 2. Cú pháp: tham số nằm ở đâu?

```text
java [JVM/launcher-options] [--source 11] TenTep.java [program-arguments...]
```

- `java`: chương trình khởi chạy JVM; khi nhận một tệp `.java`, nó chọn **source-file mode**.
- `[JVM/launcher-options]`: tùy chọn dành cho `java` hoặc JVM, **đặt trước tệp nguồn**, ví dụ `-Ddemo.mode=practice` hoặc `-Xmx256m`.
- `--source 11`: tùy chọn không bắt buộc để chạy ở mức ngôn ngữ/API Java 11, miễn là JDK đang dùng hỗ trợ mức đích này. Nó phải nằm **trước tên tệp nguồn**.
- `TenTep.java`: tệp nguồn thực tế; chương trình có điểm vào `public static void main(String[] args)`.
- `[program-arguments...]`: **tất cả các token đặt sau tên tệp nguồn** đi vào `main(String[] args)` theo đúng thứ tự.

Ví dụ:

```sh
java --source 11 ArgsEcho.java Lan 42 --verbose
```

Trong ví dụ này, `--source 11` là tùy chọn của launcher; `Lan`, `42` và `--verbose` là **ba đối số của chương trình**. `--verbose` chỉ là một chuỗi: Java không tự hiểu hay tự bật chế độ verbose. Chính code của bạn phải định nghĩa ý nghĩa cho các đối số.

> **Đừng nhầm nguồn với lớp đã biên dịch:** `java ArgsEcho.java ...` chạy tệp nguồn và biên dịch trong bộ nhớ; `java ArgsEcho ...` chạy lớp đã được biên dịch và có trên classpath. Hai cách chạy có thể truyền `args` như nhau, nhưng điều kiện khởi chạy khác nhau.

### Luồng dữ liệu

```text
Terminal / shell
     |
     | Phân tách token và xử lý dấu nháy
     v
java [tùy chọn JVM] ArgsEcho.java [đối số chương trình]
     |
     | Java launcher chạy/biên dịch nguồn trong bộ nhớ
     v
public static void main(String[] args)
     |
     +-- args[0] -> đối số thứ nhất
     +-- args[1] -> đối số thứ hai
     +-- args[2] -> đối số thứ ba
```

Thông thường, shell xử lý dấu nháy trước khi Java nhận đối số. Dấu nháy dùng để **gom văn bản thành một đối số**; nó không trở thành một phần của nội dung chuỗi nhận được.

## 3. Ví dụ 1 — nhìn chính xác các tham số Java nhận được

Tạo tệp **`ArgsEcho.java`** với toàn bộ nội dung sau:

```java
public class ArgsEcho {
    public static void main(String[] args) {
        System.out.println("Argument count: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]: <" + args[i] + ">");
        }

        System.out.println(
                "mode: " + System.getProperty("demo.mode", "none"));
    }
}
```

Mở terminal tại thư mục chứa `ArgsEcho.java` rồi chạy:

```sh
java -Ddemo.mode=practice --source 11 ArgsEcho.java "Lan Anh" 42 --verbose
```

**Đầu ra chuẩn (stdout):**

```text
Argument count: 3
args[0]: <Lan Anh>
args[1]: <42>
args[2]: <--verbose>
mode: practice
```

Phân tích:

- `args.length` là **3**. Không phải 5, vì `-Ddemo.mode=practice` và `--source 11` là tùy chọn của Java launcher, không nằm trong `args`.
- `args[0]` chứa `Lan Anh` như **một chuỗi duy nhất**, do hai từ được bao trong dấu nháy kép.
- `args[1]` chứa chuỗi `"42"`, **không phải số nguyên**. Nếu cần tính toán, chương trình phải gọi `Integer.parseInt` hay phương pháp chuyển đổi phù hợp.
- `args[2]` là chuỗi `--verbose`. Chương trình chỉ in lại vì chưa viết logic xử lý cờ.
- `System.getProperty("demo.mode", "none")` đọc **system property** được launcher thiết lập bằng `-Ddemo.mode=practice`. Đây là cơ chế khác `args`.

Nếu chạy **không có đối số**:

```sh
java --source 11 ArgsEcho.java
```

Đầu ra:

```text
Argument count: 0
mode: none
```

`args` là mảng có độ dài 0; đọc `args[0]` lúc này sẽ ném `ArrayIndexOutOfBoundsException`. Vì vậy hãy kiểm tra `args.length` trước khi truy cập phần tử.

### So sánh vị trí của `-D`

Hãy chạy:

```sh
java --source 11 ArgsEcho.java -Ddemo.mode=practice
```

Đầu ra:

```text
Argument count: 1
args[0]: <-Ddemo.mode=practice>
mode: none
```

Ở đây `-Ddemo.mode=practice` **đứng sau** `ArgsEcho.java`, nên nó là **đối số của ứng dụng**, không đặt system property.

Quy tắc đặt vị trí rất quan trọng:

| Vị trí | Ví dụ | Ai nhận? |
| --- | --- | --- |
| Trước tệp nguồn | `-Ddemo.mode=practice` | Java launcher/JVM, truy xuất trong code qua `System.getProperty` |
| Trước tệp nguồn | `-Xmx256m` | JVM, cấu hình giới hạn bộ nhớ heap |
| Trước tệp nguồn | `--source 11` | Java launcher/compiler của source-file mode |
| Sau tệp nguồn | `-Ddemo.mode=practice` | `args[0]` dưới dạng chuỗi |
| Sau tệp nguồn | `--verbose` | Một phần tử `args`; ứng dụng tự quyết định có xử lý hay không |

## 4. Dấu nháy, khoảng trắng và thứ tự đối số

Ví dụ với chương trình `ArgsEcho.java` ở phần trước:

```sh
java --source 11 ArgsEcho.java "Nguyen Van A" "0012" "--dry-run"
```

**Đầu ra:**

```text
Argument count: 3
args[0]: <Nguyen Van A>
args[1]: <0012>
args[2]: <--dry-run>
mode: none
```

Điểm cần chú ý:

- `"Nguyen Van A"` là **một đối số**, không phải ba đối số.
- `"0012"` vẫn giữ các số 0 đầu vì Java nhận một **chuỗi**; chỉ khi chuyển thành số nguyên, giá trị mới là 12.
- Chuỗi bắt đầu bằng `--` không tự trở thành “tùy chọn Java” nếu nó được đặt sau tên tệp nguồn.
- Thứ tự truyền quyết định các chỉ số `args[0]`, `args[1]`, ...; nếu đảo thứ tự, ý nghĩa của chương trình dùng đối số theo vị trí cũng đổi.
- Đường dẫn tệp nguồn chứa khoảng trắng cũng cần đặt trong dấu nháy, ví dụ `java --source 11 "demo source/ArgsEcho.java" "Lan Anh"` nếu tệp thật nằm ở đường dẫn đó.

**Mỗi shell có quy tắc riêng.** Dấu nháy kép trong những ví dụ trên là cách phổ biến trên bash, zsh, PowerShell và Windows Command Prompt để gom một đối số có khoảng trắng. Tuy nhiên, cách escape dấu nháy bên trong chuỗi, dùng biến môi trường, ký tự đặc biệt và wildcard có thể khác nhau giữa các shell. Khi cần truyền dữ liệu chứa ký tự đặc biệt, hãy kiểm tra bằng chương trình `ArgsEcho` trên chính terminal bạn dùng.

### Đối số rỗng

Ví dụ:

```sh
java --source 11 ArgsEcho.java "" value
```

Đầu ra trong các shell hỗ trợ cú pháp truyền đối số rỗng như trên:

```text
Argument count: 2
args[0]: <>
args[1]: <value>
mode: none
```

Chuỗi rỗng `""` vẫn là một phần tử của mảng; nó khác với việc **không truyền phần tử nào**. Điều này quan trọng khi phân biệt dữ liệu thiếu, dữ liệu rỗng và giá trị hợp lệ.

## 5. Ví dụ 2 — nhận tham số, chuyển kiểu và kiểm tra dữ liệu

Một tiện ích dòng lệnh thực tế không nên đọc `args[0]` hoặc chuyển số ngay khi chưa kiểm tra dữ liệu. Ví dụ sau dùng đúng một tệp và chỉ dùng các API đã có ở Java 11.

Tạo **`Receipt.java`**:

```java
public class Receipt {
    public static void main(String[] args) {
        if (args.length != 3) {
            fail("Expected exactly 3 arguments");
            return;
        }

        String item = args[0].strip();
        if (item.isBlank()) {
            fail("Item name must not be blank");
            return;
        }

        final int quantity;
        final long unitPrice;

        try {
            quantity = Integer.parseInt(args[1]);
            unitPrice = Long.parseLong(args[2]);
        } catch (NumberFormatException e) {
            fail("Quantity and unit price must be whole numbers");
            return;
        }

        if (quantity <= 0 || unitPrice < 0) {
            fail("Quantity must be positive; unit price cannot be negative");
            return;
        }

        final long total;
        try {
            total = Math.multiplyExact((long) quantity, unitPrice);
        } catch (ArithmeticException e) {
            fail("Total exceeds the supported numeric range");
            return;
        }

        System.out.println("Item: " + item);
        System.out.println("Quantity: " + quantity);
        System.out.println("Unit price: " + unitPrice);
        System.out.println("Total: " + total);
    }

    private static void fail(String message) {
        System.err.println("Error: " + message);
        System.err.println(
                "Usage: java --source 11 Receipt.java " +
                "<item> <quantity> <unit-price>");
        System.exit(2);
    }
}
```

Ở đây `<item>`, `<quantity>` và `<unit-price>` là **ký hiệu trong hướng dẫn sử dụng**; khi chạy lệnh thật hãy thay bằng giá trị, **không gõ nguyên dấu `<`/`>`**.

Chạy:

```sh
java --source 11 Receipt.java "USB cable" 3 45000
```

**Đầu ra stdout chính xác:**

```text
Item: USB cable
Quantity: 3
Unit price: 45000
Total: 135000
```

Ý nghĩa:

1. `args.length != 3` kiểm tra đúng ba giá trị theo hợp đồng giao diện CLI.
2. `args[0].strip()` bỏ khoảng trắng đầu/cuối của tên sản phẩm; `isBlank()` từ Java 11 phát hiện tên rỗng/chỉ có khoảng trắng.
3. `Integer.parseInt(args[1])` và `Long.parseLong(args[2])` chuyển chuỗi sang số nguyên. Nếu dữ liệu không hợp lệ (chẳng hạn `abc` hoặc `1.5`), `NumberFormatException` được bắt để trả thông báo rõ ràng.
4. `quantity > 0` và `unitPrice >= 0` là quy tắc nghiệp vụ của ví dụ. Sử dụng kiểu `long` cho giá theo **đơn vị nguyên**, tránh bài toán làm tròn của số thực trong bài này.
5. `Math.multiplyExact` phát hiện tràn số khi nhân; nếu giá trị vượt phạm vi `long`, chương trình báo lỗi thay vì lặng lẽ in tổng sai.
6. `System.err` dùng cho lỗi, `System.out` dùng cho kết quả bình thường. `System.exit(2)` đặt mã thoát khác 0 để công cụ chạy tự động có thể phát hiện thất bại.

Thử đầu vào sai:

```sh
java --source 11 Receipt.java "USB cable" abc 45000
```

**Thông báo trên stderr:**

```text
Error: Quantity and unit price must be whole numbers
Usage: java --source 11 Receipt.java <item> <quantity> <unit-price>
```

Ứng dụng kết thúc với mã thoát **2**. Bạn có thể kiểm tra bằng `echo $?` trên bash/zsh hoặc `$LASTEXITCODE` trên PowerShell ngay sau lệnh vừa chạy. Đầu ra này cố định với code và input đã nêu; dòng lỗi được ghi ra **stderr**, vì vậy cách hiển thị thứ tự stdout/stderr có thể khác nếu công cụ thu log gộp hai luồng.

### Tại sao không viết `int quantity = Integer.parseInt(args[1]);` ngay dòng đầu?

Vì câu lệnh đó có ít nhất hai điều kiện chưa được bảo đảm: phần tử `args[1]` có thể **không tồn tại**, hoặc chuỗi có thể **không biểu diễn số nguyên hợp lệ**. Kiểm tra số lượng, bắt lỗi chuyển kiểu, rồi xác thực miền giá trị giúp CLI dễ dùng hơn và dễ tích hợp CI/script hơn.

## 6. Trường hợp nào nên dùng kiểu đối số nào?

| Nhu cầu | Dữ liệu minh họa | Cách xử lý |
| --- | --- | --- |
| Tên, nhãn, đường dẫn | `"Lan Anh"`, `"data/report.txt"` | Đọc chuỗi `args[i]`; dùng `Path.of(args[i])` nếu thật sự cần đường dẫn |
| Số đếm | `3` | `Integer.parseInt` rồi kiểm tra giới hạn |
| Số tiền nguyên trong ví dụ đơn giản | `45000` | `Long.parseLong`; kiểm tra dấu, tràn số và quy tắc đơn vị |
| Cờ do ứng dụng định nghĩa | `--verbose`, `--dry-run` | So sánh `args[i]` với tên cờ; tự xác định lỗi hoặc mặc định |
| Tùy chọn JVM | `-Xmx256m` | Đặt **trước tệp nguồn** để launcher/JVM xử lý |
| Giá trị cấu hình JVM system property | `-Ddemo.mode=practice` | Đặt trước tệp; đọc bằng `System.getProperty` |

### Đối số theo vị trí và tùy chọn có tên

`Receipt.java` hiện dùng ba **đối số theo vị trí**. Đây là giao diện đơn giản và phù hợp ví dụ. Với nhiều tùy chọn tùy ý, một CLI thực tế có thể thiết kế các cờ như `--item`, `--quantity`, `--unit-price` hoặc dùng thư viện phân tích CLI hiện được bảo trì. Nhưng không có phép màu nào trong `main(String[] args)`: Java launcher vẫn chuyển **chuỗi gốc**, còn ứng dụng/thư viện mới phân tích quy tắc.

Ví dụ, `java --source 11 ArgsEcho.java --quantity=3` chỉ tạo một chuỗi `args[0] = "--quantity=3"`. Nó không tự tạo biến `quantity` và không chuyển `3` thành số.

## 7. Chạy từ terminal, IDE hoặc CI: giữ đúng ranh giới

**Terminal:** dùng `java --source 11 TenTep.java ...` khi muốn thử nhanh một tệp nguồn. Source-file mode biên dịch tạm trong bộ nhớ, không yêu cầu trước đó phải có tệp `.class` trên đĩa.

**IDE:** trường “Program arguments” tương ứng các đối số dành cho `main`, còn “VM options” tương ứng các tùy chọn như `-D...` hoặc `-Xmx...`. Tên trường tùy IDE, nhưng ý nghĩa hai nhóm vẫn tách biệt. Kiểm tra run configuration nếu `args.length` không đúng dự kiến.

**CI/script:** tách riêng command, arguments và cấu hình JVM; kiểm tra **exit code** trước khi xem kết quả là thành công. Nếu phụ thuộc dữ liệu tệp hoặc working directory, dùng đường dẫn và thư mục làm việc xác định thay vì giả định terminal đang ở đúng chỗ.

**Ứng dụng lớn:** source-file mode phù hợp thử nghiệm, công cụ nhỏ và học tập. Với dự án nhiều module, dependencies, bài test hoặc đóng gói phát hành, nên cấu hình build tool (Maven/Gradle) và runtime deployment rõ ràng. Cùng cơ chế `String[] args` vẫn hoạt động khi chạy main class hoặc JAR, chỉ khác hình thức gọi:

```text
java --source 11 ArgsEcho.java arg1 arg2   # Chạy trực tiếp tệp nguồn
java -cp out ArgsEcho arg1 arg2           # Chạy class đã biên dịch
java -jar app.jar arg1 arg2              # Chạy JAR có Main-Class
```

Hai lệnh sau chỉ chạy được khi **`out` đã chứa class phù hợp** hoặc **`app.jar` thực sự tồn tại và có điểm vào**; chúng minh họa vị trí truyền đối số, không phải các lệnh sẵn chạy ngay sau khi tạo tệp nguồn.

### Dữ liệu nhạy cảm

Đừng đưa password, API token hoặc thông tin bí mật vào tham số dòng lệnh: trên một số hệ thống, đối số có thể xuất hiện trong danh sách tiến trình, history, log build/CI hoặc công cụ giám sát. Với ứng dụng thật, chọn cơ chế quản lý bí mật phù hợp (secret manager, credential provider hoặc cấu hình bảo vệ truy cập) và hạn chế in lại nội dung nhạy cảm. Chương trình `ArgsEcho` cố ý **in mọi đối số**, vì vậy chỉ dùng dữ liệu thử nghiệm không nhạy cảm.

## 8. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `java: command not found` hoặc không nhận `--source` | Chưa cài JDK phù hợp, `PATH` trỏ sai, hoặc bản launcher không hỗ trợ cách gọi | Kiểm tra `java --version`, `javac --version`, `java --help` và môi trường đang chạy |
| `Could not find or load main class ArgsEcho.java` | Lỗi tên/đường dẫn tệp hoặc đang dùng launcher không đúng chế độ | Xác nhận tệp tồn tại, đúng tên, đúng working directory và JDK có hỗ trợ source-file mode |
| `ArrayIndexOutOfBoundsException` | Truy cập `args[i]` khi chưa truyền đủ giá trị | Kiểm tra `args.length` trước |
| `NumberFormatException` | Giá trị thực tế không chuyển được thành số nguyên | Bắt ngoại lệ và báo hướng dẫn nhập hợp lệ |
| Một tên có khoảng trắng bị tách thành nhiều đối số | Thiếu dấu nháy khi chạy từ shell | Bao giá trị bằng dấu nháy theo shell đang dùng |
| `-Dkey=value` xuất hiện trong `args` | Tùy chọn đặt **sau** tệp nguồn | Chuyển `-D...` đến **trước** tệp nguồn nếu muốn là system property |
| Gõ `--help` nhưng chương trình không hiện trợ giúp | Ứng dụng chưa xử lý cờ này | Thêm xử lý `--help` vào code hoặc dùng thư viện parser |
| Kết quả số sai/âm bất thường | Thiếu validation hoặc tràn số | Kiểm tra phạm vi đầu vào và dùng `Math.multiplyExact` khi thích hợp |
| Mã nguồn chạy ở máy này nhưng lỗi phiên bản ở máy khác | Dùng JDK khác nhau hoặc mức `--source` không được hỗ trợ | Đồng bộ toolchain và kiểm tra mức nguồn được JDK hiện tại chấp nhận |

**Lưu ý về `--source`:** giá trị release được hỗ trợ thay đổi qua các phiên bản JDK; JDK tương lai có thể bỏ hỗ trợ biên dịch mức quá cũ. Luôn kiểm tra trợ giúp của bộ công cụ thực tế thay vì mặc định `--source 11` được hỗ trợ mãi mãi. Nếu bài học yêu cầu đúng API Java 11, dùng JDK còn bảo trì và xác nhận compiler vẫn hỗ trợ mức 11.

## 9. Bài tập tự kiểm tra

**Bài 1 — Đếm và giữ nguyên văn bản.** Chạy:

```sh
java --source 11 ArgsEcho.java "Hello Java" 007 --dry-run
```

Hãy dự đoán `args.length` và từng `args[i]` trước khi chạy. Đối chiếu: có **3 đối số**, lần lượt `Hello Java`, `007` và `--dry-run`. Không đối số nào tự chuyển thành số hoặc cờ boolean.

**Bài 2 — Phân biệt option của JVM.** Chạy `ArgsEcho` hai lần, một lần đặt `-Ddemo.mode=study` **trước** tên tệp nguồn và một lần đặt **sau**. Giải thích vì sao dòng `mode:` và `Argument count:` khác nhau.

**Bài 3 — Kiểm thử đầu vào sai.** Chạy `Receipt` với **0 đối số**, với `quantity=abc`, với `quantity=0`, với `unit-price=-1` và với ba đối số hợp lệ. Xác nhận thông báo stderr, mã thoát khác 0 ở trường hợp lỗi, và đúng `Total` ở trường hợp hợp lệ.

**Bài 4 — Mở rộng CLI.** Thêm khả năng dùng một cờ `--help`. Khi người dùng gọi `java --source 11 Receipt.java --help`, chương trình in hướng dẫn và thoát thành công; các đầu vào khác vẫn cần được kiểm tra. Viết kiểm thử cho việc có/không có cờ này. Gợi ý: xử lý `args.length == 1 && "--help".equals(args[0])` **trước** kiểm tra số đối số bắt buộc.

### Checklist hoàn thành

- [ ] Đã gọi `java --source 11 TênTệp.java ...` với JDK đang được bảo trì và xác nhận đúng tệp.
- [ ] Giải thích được ý nghĩa `args.length`, `args[0]` và thứ tự đối số.
- [ ] Chạy được ví dụ có khoảng trắng, số ở dạng chuỗi và cờ bắt đầu bằng `--`.
- [ ] Phân biệt `-D...`/`-Xmx...` đặt trước tệp với đối số sau tệp.
- [ ] Có kiểm tra số lượng, xử lý lỗi chuyển kiểu, stderr và exit code.
- [ ] Không đưa dữ liệu bí mật vào đối số hoặc log thử nghiệm.

## 10. Tài liệu tham khảo đang áp dụng

- [dev.java — Launching Simple Source-Code Programs](https://dev.java/learn/first-steps/first-java-code/launch-simple-source-code-programs/) — hướng dẫn chính thức về chạy nguồn trực tiếp và truyền đối số.
- [Oracle JDK 25 — The `java` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html) — cú pháp launcher, source-file mode, `--source` và cách xử lý đối số sau tên tệp.
- [OpenJDK JEP 330 — Launch Single-File Source-Code Programs](https://openjdk.org/jeps/330) — cơ chế được giới thiệu ở Java 11.
- [Java SE 11 — String API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html) và [Integer API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Integer.html) — các phương thức `strip`, `isBlank` và `parseInt` dùng trong ví dụ.

**Điểm cần nhớ:** Với chương trình nguồn Java 11, **tùy chọn Java/JVM đặt trước tệp nguồn**, còn **mọi đối số ứng dụng đặt sau tệp nguồn** đi vào `main(String[] args)` dưới dạng chuỗi, theo đúng thứ tự. Chính ứng dụng chịu trách nhiệm diễn giải, kiểm tra và xử lý lỗi của các chuỗi ấy.