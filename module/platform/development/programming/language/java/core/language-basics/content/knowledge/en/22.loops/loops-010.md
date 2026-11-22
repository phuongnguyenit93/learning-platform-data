# Chọn `while`, `do-while` hoặc `for` theo bài toán — Java 17+

Java có ba cấu trúc lặp cơ bản. **Chọn vòng lặp dựa vào thời điểm kiểm tra điều kiện và cách xác định điểm dừng**, không phải vì một cú pháp luôn chạy nhanh hơn cú pháp khác:

- **`for`**: phù hợp khi quản lý chỉ số, biến đếm hoặc các bước khởi tạo–kiểm tra–cập nhật thuộc về cùng một vòng.
- **`while`**: phù hợp khi chưa biết trước số lượt, chỉ tiếp tục khi điều kiện còn đúng; thân **có thể chạy 0 lần**.
- **`do-while`**: phù hợp khi cần thực hiện thân **ít nhất một lần** trước khi quyết định lặp tiếp, chẳng hạn yêu cầu nhập dữ liệu lần đầu.

## 1. Bảng chọn nhanh

| Tình huống | Nên cân nhắc | Lý do |
| --- | --- | --- |
| Duyệt các chỉ số `0..n-1` | `for` | Khởi tạo, điều kiện và cập nhật biến đếm nằm cùng một chỗ |
| Lặp đúng `n` lượt | `for` | Số lượt và biên được biểu đạt rõ |
| Đọc đến khi hết dữ liệu/đến dấu kết thúc | `while` | Số lượt không cố định; có thể không có dữ liệu nào |
| Chờ trạng thái thay đổi, có giới hạn số lần thử | `while` hoặc `for` | Dừng khi điều kiện đạt hoặc hết lượt |
| Hiển thị yêu cầu nhập rồi kiểm tra để nhập lại | `do-while` | Thân cần chạy ít nhất một lần |
| Muốn thực thi thân 0 lần khi điều kiện ban đầu sai | `while` hoặc `for` | Cả hai đều kiểm tra trước |
| Duyệt giá trị từng phần tử mảng, không cần vị trí | Enhanced `for` | Đọc dễ hơn, không quản lý chỉ số thủ công |

**Không có quy tắc bắt buộc**: cùng một thuật toán có thể viết đúng bằng nhiều loại vòng lặp. Chọn cấu trúc làm nổi bật **điều kiện dừng**, giảm rủi ro quên cập nhật và dễ kiểm thử.

## 2. Ba cú pháp và thứ tự thực thi

### `for` — biểu đạt các bước biến đếm

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

Thứ tự: **khởi tạo một lần → kiểm tra → thân → cập nhật → kiểm tra lại**. Khi điều kiện sai ngay từ đầu, thân không chạy. Nếu biến `i` được khai báo ngay trong phần khởi tạo, nó không còn nằm trong phạm vi sử dụng sau câu lệnh `for`.

### `while` — kiểm tra trước khi chạy thân

~~~java
int remaining = 3;
while (remaining > 0) {
    System.out.println(remaining);
    remaining--;
}
~~~

Thứ tự: **kiểm tra → thân → kiểm tra lại**. Người viết thường chịu trách nhiệm cập nhật trạng thái trong thân; nếu `remaining--` bị quên, vòng có thể không kết thúc. `while` phù hợp khi điểm dừng phụ thuộc dữ liệu/trạng thái chứ không chỉ một chỉ số đếm.

### `do-while` — chạy trước rồi mới kiểm tra

~~~java
int attempt = 0;
do {
    attempt++;
    System.out.println("attempt=" + attempt);
} while (attempt < 2);
~~~

Thứ tự: **thân → kiểm tra → thân...**; thân chạy ít nhất một lần nếu đi vào vòng lặp bình thường. Cú pháp có **dấu chấm phẩy bắt buộc sau `while (condition);`**. Khác `while`, dù điều kiện ban đầu đã false, thân vẫn được chạy một lần trước lần kiểm tra đầu tiên.

| Cấu trúc | Kiểm tra trước thân đầu tiên? | Số lượt tối thiểu | Nơi cập nhật thường gặp |
| --- | --- | ---: | --- |
| Basic `for` | Có | 0 | Phần cập nhật trong đầu vòng |
| `while` | Có | 0 | Trong thân, hoặc từ thay đổi trạng thái |
| `do-while` | Không | 1 | Trong thân trước khi kiểm tra |

## 3. Demo Java 17+ tự chứa, runnable CLI

Tạo tệp UTF-8 tên **`ChooseLoopDemo.java`**:

~~~java
public class ChooseLoopDemo {
    static void countedFor() {
        for (int i = 0; i < 3; i++) {
            System.out.println("for=" + i);
        }
    }

    static void unknownAttemptsWhile() {
        int attempts = 0;
        boolean connected = false;
        while (!connected && attempts < 3) {
            attempts++;
            System.out.println("try=" + attempts);
            connected = attempts == 2;
        }
        System.out.println("connected=" + connected);
        System.out.println("attempts=" + attempts);
    }

    static void promptDoWhile() {
        String[] inputs = {"", " An "};
        int index = 0;
        String name;
        do {
            name = inputs[index++];
            System.out.println("entry="
                    + (name.isBlank() ? "blank" : name.trim()));
        } while (name.isBlank() && index < inputs.length);
        System.out.println("name=" + name.trim());
    }

    static void initialFalse() {
        int available = 0;
        int whileVisits = 0;
        while (available > 0) {
            whileVisits++;
        }

        int doVisits = 0;
        do {
            doVisits++;
        } while (available > 0);

        System.out.println("whileVisits=" + whileVisits);
        System.out.println("doVisits=" + doVisits);
    }

    static void readUntilSentinel() {
        String[] tokens = {"4", "bad", "6", "stop", "100"};
        int index = 0;
        int total = 0;

        while (index < tokens.length) {
            String token = tokens[index++];
            if (token.equals("stop")) {
                System.out.println("sentinel=stop");
                break;
            }
            try {
                total += Integer.parseInt(token);
            } catch (NumberFormatException ex) {
                System.out.println("invalid=" + token);
            }
        }
        System.out.println("total=" + total);
        System.out.println("consumed=" + index);
    }

    static void forContinue() {
        for (int i = 0; i < 4; i++) {
            if (i == 1) {
                continue;
            }
            System.out.println("keep=" + i);
        }
    }

    static void enhancedFor() {
        int total = 0;
        for (int value : new int[] {2, 4, 6}) {
            total += value;
        }
        System.out.println("enhancedTotal=" + total);
    }

    public static void main(String[] args) {
        System.out.println("== counted for ==");
        countedFor();

        System.out.println("== conditional while ==");
        unknownAttemptsWhile();

        System.out.println("== do-while prompt ==");
        promptDoWhile();

        System.out.println("== initially false ==");
        initialFalse();

        System.out.println("== sentinel while ==");
        readUntilSentinel();

        System.out.println("== continue in for ==");
        forContinue();

        System.out.println("== enhanced for ==");
        enhancedFor();
        System.out.println("done");
    }
}
~~~

Sử dụng **JDK 17+**. Mở PowerShell (Windows) hoặc Bash (Linux/macOS) tại thư mục chứa file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 ChooseLoopDemo.java
java ChooseLoopDemo
~~~

**Exact expected stdout** của riêng lệnh `java ChooseLoopDemo`:

~~~text
== counted for ==
for=0
for=1
for=2
== conditional while ==
try=1
try=2
connected=true
attempts=2
== do-while prompt ==
entry=blank
entry=An
name=An
== initially false ==
whileVisits=0
doVisits=1
== sentinel while ==
invalid=bad
sentinel=stop
total=10
consumed=4
== continue in for ==
keep=0
keep=2
keep=3
== enhanced for ==
enhancedTotal=12
done
~~~

`java -version` và `javac -version` cho thông tin phiên bản phụ thuộc máy, không thuộc stdout cố định. Chương trình mô phỏng dữ liệu sẵn để kết quả không phụ thuộc bàn phím hay mạng.

## 4. Chọn theo điều kiện đầu vào, không chỉ số lượt

### Đã biết số lượt hoặc giới hạn chỉ số: `for`

~~~java
int[] values = {10, 20, 30};
for (int i = 0; i < values.length; i++) {
    System.out.println(values[i]);
}
~~~

Biên đúng là `i < values.length`, không phải `<=`. Với mảng rỗng, vòng lặp chạy **0 lượt**. Enhanced `for (int value : values)` còn gọn hơn nếu chỉ cần giá trị, không cần chỉ số hoặc thay đổi phần tử qua vị trí.

### Lặp phụ thuộc trạng thái: `while`

~~~java
int attempts = 0;
boolean success = false;
while (!success && attempts < 3) {
    attempts++;
    success = tryOnce(attempts);
}
~~~

`tryOnce` ở đây chỉ là tên mô tả một phương thức nghiệp vụ do ứng dụng cung cấp; ví dụ **chạy được** trong phần 3 đã dùng điều kiện giả lập `attempts == 2`. Thực tế nên đặt giới hạn để tránh thử vô hạn, và xác định rõ một lần thử có được thực hiện nếu trạng thái thành công ngay từ đầu hay không.

### Phải thực hiện lần đầu rồi mới biết nên lặp không: `do-while`

~~~java
String input;
do {
    input = askForName(); // Phương thức lấy dữ liệu do ứng dụng cung cấp.
} while (input == null || input.isBlank());
~~~

Đây là hình thức thường thấy khi cần hiển thị lời nhắc ít nhất một lần. Trong ứng dụng thực, cần thêm chính sách hủy, đóng input hoặc giới hạn thử; nếu luôn nhận dữ liệu không hợp lệ, vòng có thể không bao giờ kết thúc. Phương thức `askForName()` trong ví dụ ý tưởng này **không thuộc file demo**.

## 5. Có thể chuyển đổi `for` và `while`, nhưng phải giữ thứ tự

Hai đoạn sau thường tương đương nếu không có điều khiển luồng đặc biệt:

~~~java
for (int i = 0; i < 3; i++) {
    System.out.println(i);
}
~~~

~~~java
int i = 0;
while (i < 3) {
    System.out.println(i);
    i++;
}
~~~

Nhưng **`continue` làm thay đổi cách chuyển đổi**:

~~~java
for (int i = 0; i < 4; i++) {
    if (i == 1) {
        continue; // Java vẫn chạy phần cập nhật i++ của for.
    }
    System.out.println(i);
}
~~~

Nếu chép sang `while` rồi đặt `i++` sau `continue`, vòng có thể lặp mãi với `i == 1` vì cập nhật bị bỏ qua. Khi chuyển đổi, bảo đảm mọi đường tiếp tục vòng đều **tiến triển**.

| Lệnh trong thân | Basic `for` | `while` / `do-while` |
| --- | --- | --- |
| `continue` nhắm đến vòng này | Chạy phần cập nhật của `for` rồi kiểm tra điều kiện | Chuyển tới kiểm tra điều kiện; tự bảo đảm trạng thái được cập nhật |
| `break` | Thoát vòng ngay, không chạy cập nhật `for` | Thoát vòng ngay |
| `return` hoặc `throw` | Thoát phương thức hoặc ném ngoại lệ | Tác dụng tương tự |

`do-while` còn khác ở bước kiểm tra **sau thân**, vì thế không thể đổi máy móc thành `while` mà vẫn giữ đúng hành vi nếu điều kiện sai từ đầu.

## 6. Lưu ý về độ an toàn và khả năng đọc

- **Điều kiện phải là `boolean`**, không dùng `while (1)` hay `for (; number;)` như cách coi số là boolean trong một số ngôn ngữ.
- **Dấu `;` có vị trí quan trọng**: basic `for` có hai dấu `;` trong phần đầu; `do-while` có `;` ở cuối; vô tình đặt `;` sau `while (condition)` hoặc `for (...)` sẽ tạo **thân rỗng**.
- **Có điểm dừng rõ ràng**: thay đổi biến đếm/trạng thái, tiêu thụ dữ liệu hoặc dùng `break`/`return` có chủ đích. `while (true)` không tự sai, nhưng phải có chiến lược thoát.
- **Đừng dựa vào độ dài của vòng để chọn cấu trúc**: ba cú pháp không có thứ hạng tốc độ cố định. Hãy ưu tiên biểu đạt đúng hành vi và dễ bảo trì.
- **Phạm vi biến**: `int i` khai báo trong phần đầu `for` không thể dùng ngoài vòng; biến khai báo trước `while` thường vẫn trong phạm vi sau vòng.

## 7. Bài tập tự kiểm tra

1. Muốn duyệt mọi phần tử mảng bằng chỉ số `0..length-1`, nên chọn gì?  
   *Gợi ý:* `for` với `i < array.length`.
2. Muốn đọc dữ liệu cho tới khi gặp `"stop"`, chưa biết bao nhiêu mục, chọn gì?  
   *Gợi ý:* `while`, cập nhật vị trí hoặc đọc mục tiếp theo mỗi lượt.
3. Muốn hiển thị yêu cầu nhập **ít nhất một lần** rồi kiểm tra hợp lệ, chọn gì?  
   *Gợi ý:* `do-while`.
4. Điều kiện sai ngay từ đầu, ba dạng có số lượt tối thiểu lần lượt là bao nhiêu?  
   *Đáp án:* Basic `for` = 0, `while` = 0, `do-while` = 1.
5. Khi chuyển `for` có `continue` sang `while`, dễ quên điều gì?  
   *Đáp án:* Cập nhật trạng thái trước khi kiểm tra tiếp.
6. Nếu không cần chỉ số khi duyệt mảng, cú pháp nào làm mã đơn giản hơn?  
   *Gợi ý:* Enhanced `for`.

## Checklist

- [ ] Chọn **`for`** khi các bước đếm/duyệt chỉ số rõ ràng.
- [ ] Chọn **`while`** khi điều kiện được kiểm tra **trước** và số lượt tùy trạng thái.
- [ ] Chọn **`do-while`** khi thân cần chạy **ít nhất một lần**.
- [ ] Kiểm tra biên chỉ số, điều kiện đầu và cơ chế tiến triển.
- [ ] Hiểu `continue`/`break` trước khi chuyển đổi loại vòng lặp.
- [ ] Biết phân biệt basic `for` với enhanced `for`.

**Kết luận:** Hãy chọn theo **ngữ nghĩa bài toán**: `for` cho vòng đếm rõ ràng, `while` cho điều kiện tiếp diễn kiểm tra trước và `do-while` cho bước thực thi đầu tiên bắt buộc. Kiểm tra kỹ điều kiện dừng và cập nhật sẽ quan trọng hơn việc cố dùng một loại vòng lặp cho mọi trường hợp.
