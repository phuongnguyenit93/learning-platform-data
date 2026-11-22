# Vai trò của `StringBuffer` trong mã cần đồng bộ

`StringBuffer` là lớp biểu diễn một dãy ký tự **có thể thay đổi** (*mutable*) trong Java. Nó cung cấp những thao tác quen thuộc như `append`, `insert`, `delete`, `replace`, `reverse` và `toString`. Điểm phân biệt cốt lõi với `StringBuilder` là **nhiều phương thức thao tác của `StringBuffer` được đồng bộ hóa (`synchronized`)**, giúp bảo vệ trạng thái của **cùng một buffer** khi nhiều luồng gọi các thao tác đó.

Tuy nhiên, câu «`StringBuffer` thread-safe» phải được hiểu **đúng phạm vi**:

- Mỗi thao tác đã được đồng bộ trên **cùng đối tượng `StringBuffer`** được tuần tự hóa qua khóa (monitor) của đối tượng đó.
- Một chuỗi gồm nhiều lời gọi riêng lẻ, như **kiểm tra độ dài rồi mới append**, **không tự động nguyên tử**; luồng khác có thể xen vào giữa hai lần gọi.
- Đầu vào là một `CharSequence` hoặc mảng mutable được chia sẻ có thể cần cơ chế bảo vệ **riêng**; đồng bộ trên buffer đích không khóa mọi đối tượng nguồn.
- Nếu không cần chia sẻ một vùng văn bản đang thay đổi giữa nhiều luồng, `StringBuilder` thường đơn giản và phù hợp hơn. `StringBuffer` không phải lựa chọn mặc định cho mọi thao tác nối chuỗi.

Bài học tập trung vào **vai trò đồng bộ** của `StringBuffer`, những bảo đảm nó cung cấp, giới hạn của các bảo đảm đó và cách chọn thiết kế đúng.

## 1. So sánh nhanh `String`, `StringBuilder` và `StringBuffer`

| Đặc điểm | `String` | `StringBuilder` | `StringBuffer` |
| --- | --- | --- | --- |
| Nội dung có thể sửa tại chỗ? | Không; bất biến | Có | Có |
| `append(...)` thay đổi chính đối tượng? | Không có API `append` mutable như builder | Có | Có |
| Đồng bộ hóa nhiều thao tác trên cùng đối tượng? | Không cần khóa để bảo vệ nội dung bất biến | Không tự đồng bộ hóa | Nhiều phương thức được `synchronized` |
| Phù hợp điển hình | Giá trị văn bản đã hoàn thiện, truyền chia sẻ nội dung | Xây dựng văn bản cục bộ trong một luồng | Bộ đệm ký tự mutable dùng chung khi cần đồng bộ từng thao tác |
| Tác động của nhiều luồng ghi cùng lúc | Không thể sửa nội dung `String` | Có nguy cơ race và trạng thái sai | Các thao tác đồng bộ trên cùng buffer được tuần tự hóa, nhưng nghiệp vụ nhiều bước vẫn cần phối hợp |

Cả `StringBuilder` và `StringBuffer` kế thừa từ `AbstractStringBuilder` theo thiết kế của JDK, cùng triển khai các giao diện liên quan đến dãy ký tự và bổ sung dữ liệu. **Không nên viết code phụ thuộc vào lớp nội bộ/triển khai**; hãy dựa vào API công khai và hợp đồng đồng bộ của lớp được sử dụng.

Chọn `StringBuffer` không đồng nghĩa với việc mọi biến, luồng, mảng nguồn hoặc đối tượng liên quan đều tự trở nên an toàn khi chạy đồng thời.

## 2. `synchronized` trên buffer bảo vệ điều gì?

Một số phương thức của `StringBuffer` được khai báo `synchronized`, chẳng hạn các thao tác thêm, sửa, đọc và truy cập trạng thái cụ thể. Khi một luồng đang thực thi một phương thức đồng bộ của một `StringBuffer`, một luồng khác muốn đi vào phương thức đồng bộ dùng **cùng khóa của chính buffer đó** phải đợi.

Hình dung có hai luồng cùng trỏ tới một buffer:

```text
Thread A ─┐
          ├──> StringBuffer shared
Thread B ─┘          │
                     └─ monitor của shared
                        (mỗi lần chỉ một luồng giữ khóa này)
```

Ví dụ:

```java
StringBuffer shared = new StringBuffer();
shared.append("A");
shared.append("B");
```

Mỗi `append` ở trên ghi vào đối tượng `shared`. Nếu các luồng khác đồng thời dùng `shared.append(...)`, các lần append được đồng bộ với nhau trên buffer này. Không có nghĩa toàn chương trình chỉ có một luồng chạy, hoặc hai lần `append` liên tiếp của cùng một luồng được gộp thành một giao dịch.

**Monitor của từng đối tượng là riêng biệt:** hai `StringBuffer` khác nhau có hai khóa riêng. Việc đồng bộ phương thức của buffer X không khóa buffer Y, cũng không khóa biến `StringBuilder` khác.

### Đồng bộ còn liên quan tới khả năng nhìn thấy dữ liệu

Ngoài loại trừ tương hỗ (*mutual exclusion*), monitor `synchronized` tham gia quy tắc **happens-before** của Java Memory Model. Việc một luồng nhả khóa monitor của một đối tượng xảy ra trước việc một luồng khác khóa lại **chính monitor đó** về mặt bảo đảm nhìn thấy dữ liệu phù hợp.

Trong thực hành, các thao tác đồng bộ trên cùng `StringBuffer` không chỉ tránh hai lần ghi đồng thời làm hỏng trạng thái nội bộ mà còn góp phần bảo đảm các thao tác sau nhìn thấy cập nhật được bảo vệ bởi cùng cơ chế khóa.

Nhưng nếu bạn đọc/ghi các biến khác ngoài khóa này, hoặc phối hợp nhiều tài nguyên, **không có một quy tắc tự động** rằng mọi trạng thái nghiệp vụ đều nhất quán chỉ nhờ một lời gọi `buffer.append(...)`.

## 3. Ví dụ nhiều luồng: mỗi lời gọi `append` được bảo vệ

Khi nhiều luồng cùng thêm một ký tự cố định vào **cùng đối tượng `StringBuffer`**, số lượng ký tự cuối cùng có thể kiểm tra được sau khi tất cả luồng đã kết thúc.

Tạo tệp `ConcurrentBufferAppendDemo.java`:

```java
public class ConcurrentBufferAppendDemo {
    public static void main(String[] args) throws InterruptedException {
        final int threadCount = 4;
        final int repeats = 1000;
        StringBuffer shared = new StringBuffer();
        Thread[] threads = new Thread[threadCount];

        for (int i = 0; i < threadCount; i++) {
            threads[i] = new Thread(() -> {
                for (int j = 0; j < repeats; j++) {
                    shared.append('x');
                }
            });
        }

        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        String result = shared.toString();
        System.out.println(result.length());
        System.out.println(result.chars().allMatch(ch -> ch == 'x'));
    }
}
```

Biên dịch/chạy trên JDK 17 trở lên:

```bash
javac ConcurrentBufferAppendDemo.java
java ConcurrentBufferAppendDemo
```

Kết quả:

```text
4000
true
```

Tại sao kết quả xác định?

1. Có bốn luồng, mỗi luồng gọi `append('x')` đúng 1.000 lần.
2. Các lời gọi `append` trên một `StringBuffer` được đồng bộ nên không có việc cập nhật trạng thái nội bộ của buffer chồng chéo nhau.
3. `join()` giúp luồng `main` chỉ đọc kết quả **sau khi** từng luồng hoàn tất; các hành động của luồng đã hoàn tất có quan hệ happens-before với sự trở về thành công của `join()`.
4. Tất cả ký tự được thêm đều là `'x'`, nên thứ tự xen kẽ không ảnh hưởng nội dung; kết quả có độ dài 4.000 và mọi code unit đều là `x`.

Nếu bốn luồng thêm **các chuỗi khác nhau**, thứ tự xuất hiện giữa các lời gọi phụ thuộc lịch chạy. `StringBuffer` bảo đảm tính an toàn của từng thao tác chứ **không** hứa luồng nào append trước theo thời gian yêu cầu hay ID của luồng.

Đừng dùng chính xác thứ tự giao nhau của các luồng làm điều kiện kiểm thử nếu ứng dụng không có cơ chế sắp thứ tự riêng.

## 4. `StringBuilder` khác gì khi dùng chung qua các luồng?

`StringBuilder` có API tạo chuỗi gần tương đương nhưng **không tự đồng bộ hóa** các thao tác mutable. Nếu nhiều luồng gọi `append` trên cùng một `StringBuilder` mà không có quan hệ đồng bộ thích hợp, chương trình có **data race** và không có bảo đảm rằng số lượng hay nội dung kết quả sẽ đúng.

Không nên viết một bài kiểm thử giả định `StringBuilder` «chắc chắn sẽ mất ký tự» ở mỗi lần chạy. Race có thể có lúc biểu hiện, lúc không; kết quả phụ thuộc lịch chạy, tối ưu JIT và môi trường. Điều quan trọng là **thiết kế chia sẻ không có bảo đảm thread-safety**, không phải chứng minh lỗi bằng một lần chạy may rủi.

Ví dụ đối chiếu về **quyền sở hữu**, không cần chia sẻ mutable builder:

```java
// Mỗi luồng sở hữu builder riêng trong phương thức.
static String buildLine(int id) {
    StringBuilder local = new StringBuilder();
    local.append("thread=").append(id);
    return local.toString();
}
```

Đây là đoạn phương thức minh họa, chưa phải chương trình độc lập. Mỗi lần gọi tạo một builder mới chỉ được thao tác trong chính lần gọi đó; kết quả trả về là `String` bất biến. Cách chia sẻ **chuỗi kết quả** thay vì chia sẻ builder mutable thường giảm nhu cầu đồng bộ.

Không phải mọi tác vụ đa luồng đều cần `StringBuffer`. Câu hỏi trước tiên là: **có thực sự cần nhiều luồng sửa cùng một đối tượng dãy ký tự hay không?**

## 5. Bốn ranh giới thiết kế cần nhận biết

Một đối tượng `StringBuffer` giúp điều phối **từng lần sửa nội dung**. Khi đặt nó vào một chương trình thực tế, hãy phân biệt ranh giới của thao tác, dữ liệu nguồn, quyền sở hữu và bản kết quả.

| Nhu cầu | Từng phương thức `StringBuffer` đã đủ? | Thiết kế bổ sung |
| --- | --- | --- |
| Nhiều luồng chỉ thêm một đoạn độc lập bằng `append(String)` | Có, đối với từng lần thêm vào cùng buffer | Không giả định thứ tự giữa các luồng |
| Kiểm tra điều kiện rồi mới sửa, như giới hạn độ dài | Chưa đủ | Khóa xuyên suốt bước kiểm tra và cập nhật |
| Tạo một bản ghi từ nhiều lần `append` | Chưa đủ | Dựng một `String` đầy đủ rồi append một lần, hoặc khóa cả nhóm |
| Chép từ một `CharSequence` nguồn đang thay đổi | Chưa đủ | Quy ước đồng bộ trên nguồn hoặc lấy `String` ổn định trước |
| Giao giá trị văn bản cho bên đọc về sau | Không nên giao chính buffer mutable | Trả `buffer.toString()` ở thời điểm mong muốn |

### Một thao tác độc lập khác với một quy tắc nghiệp vụ

Ví dụ kiểm tra độ dài rồi thêm ký tự gồm hai lời gọi riêng:

```java
// Có thể vượt giới hạn khi nhiều luồng cùng kiểm tra trước lúc ghi.
if (shared.length() < 3) {
    shared.append('x');
}
```

Nếu giới hạn là bất biến bắt buộc, phải dùng cùng một monitor cho cả hai bước:

```java
synchronized (shared) {
    if (shared.length() < 3) {
        shared.append('x');
    }
}
```

Lỗi và cách tái hiện bằng `CountDownLatch` được triển khai đầy đủ ở bài **“Đồng bộ từng phương thức không bảo đảm nguyên tử cho cả chuỗi thao tác”**; bài **“Chọn khóa chung”** phân tích sự khác nhau giữa monitor của buffer và khóa riêng của lớp quản lý dữ liệu.

### Một bản ghi có thể hoàn chỉnh ngay từ đầu

```java
String record = "[" + userId + "] done\n"; // Dữ liệu cục bộ, đã hoàn thiện.
shared.append(record);                    // Một lần sửa buffer chung.
```

Làm vậy giữ từng bản ghi liền mạch khi các luồng đều append bằng một lời gọi trên cùng buffer. **Thứ tự các bản ghi vẫn không được bảo đảm**. Nếu nhiều trường hoặc điều kiện cũng phải cập nhật cùng bản ghi, cần bảo vệ trọn bất biến đó.

### Đích được đồng bộ không làm nguồn tự ổn định

Khi đọc một `StringBuilder` hoặc `CharSequence` mutable khác, phải bảo đảm writer không thay đổi nó trong lúc copy. Có thể chụp một `String` bất biến dưới quy ước khóa mà mọi bên đều tuân thủ, rồi sử dụng snapshot nhiều lần. Bài **“Đối tượng nguồn khả biến khi append hoặc insert”** đi sâu vào overload, vùng `start/end`, `CharBuffer` và tự tham chiếu.

### Giữ quyền sở hữu của buffer

`final StringBuffer` chỉ cố định tham chiếu, nội dung vẫn sửa được. Khi đối tượng là trạng thái nội bộ của một lớp, hãy cân nhắc để trường `private`, cung cấp API thao tác theo bất biến và trả `String` cho nơi chỉ cần đọc. Bài **“Chuyển từ StringBuffer sang String”** giải thích snapshot, xử lý `null` và Unicode.


## 6. Khi nào nên chọn `StringBuffer`?

### Nên cân nhắc `StringBuffer`

- **Có một bộ đệm mutable thực sự được chia sẻ**, và nhiều luồng cần gọi những thao tác trên chính buffer đó.
- Bạn muốn tận dụng các phương thức đồng bộ sẵn có và hiểu rõ ranh giới của từng thao tác.
- Bạn đang bảo trì một API hoặc thư viện cũ đã sử dụng `StringBuffer` làm một phần hợp đồng, và việc thay đổi kiểu có thể ảnh hưởng tương thích.
- Dữ liệu được xây dựng tuần tự theo các lời gọi cần tương tác với những API vốn nhận `StringBuffer`.

### Thường chọn giải pháp khác

- **Mỗi tác vụ chỉ ghép chuỗi trong một luồng:** chọn `StringBuilder` cục bộ.
- **Chỉ cần chia sẻ giá trị văn bản không thay đổi:** dùng `String` bất biến.
- **Cần cả một giao dịch nhiều thao tác trên builder:** dù chọn `StringBuffer` vẫn cần khóa bao quanh giao dịch; hoặc dùng `StringBuilder` có một khóa ngoài được áp dụng nhất quán.
- **Cần lưu nhiều sự kiện theo đúng thứ tự, truyền thông điệp hoặc batching:** cân nhắc queue, immutable records, một luồng tổng hợp hoặc cấu trúc đồng thời phù hợp, thay vì biến `StringBuffer` thành một hệ thống hàng đợi.
- **Luồng nào cũng thường xuyên tranh cùng buffer:** khóa đơn có thể gây contention. Cân nhắc xây dựng chuỗi cục bộ rồi chỉ đồng bộ tại điểm hợp nhất.

Không nên khẳng định `StringBuffer` luôn «chậm» hoặc `StringBuilder` luôn «nhanh» trên mọi JVM và mọi tình huống. `StringBuffer` có overhead liên quan đồng bộ, nhưng hiệu năng còn phụ thuộc tối ưu JVM, contention, kích thước dữ liệu và thiết kế. Chọn theo yêu cầu tính đúng trước, đo thực tế nếu hiệu năng quan trọng.

## 7. Các hiểu nhầm thường gặp

**Nhầm 1 — «Dùng `StringBuffer` là cả chương trình thread-safe».** Lớp này chỉ cung cấp cơ chế đồng bộ cho thao tác trên buffer; các biến và tài nguyên khác phải được bảo vệ riêng.

**Nhầm 2 — «`length()` thread-safe và `append()` thread-safe nên `if (...) append(...)` cũng thread-safe».** Đây là thao tác ghép. Cần một vùng tới hạn bao trùm cả kiểm tra lẫn cập nhật.

**Nhầm 3 — «`append(...).append(...)` tự khóa suốt chuỗi».** Mỗi lời gọi có phạm vi đồng bộ riêng. Có thể có thao tác của luồng khác xen giữa.

**Nhầm 4 — «`StringBuffer` quyết định thứ tự của các luồng».** Nó đồng bộ từng thao tác; thứ tự các luồng lấy được khóa phụ thuộc lịch chạy, không được định trước theo ID hoặc thứ tự gọi `start()`.

**Nhầm 5 — «Lấy `StringBuffer` làm tham số là tự an toàn với nguồn mutable».** Đích và nguồn là các đối tượng khác nhau. Cần bảo đảm quan sát nguồn ổn định nếu nguồn được chia sẻ và sửa đồng thời.

**Nhầm 6 — «`final StringBuffer` là bất biến».** `final` cố định tham chiếu, không chặn thay đổi nội dung của buffer.

**Nhầm 7 — «Có thể kiểm tra race bằng một lần chạy thử và nếu đúng thì an toàn».** Lỗi đồng thời có thể không xuất hiện trong một lần thực thi; dựa vào hợp đồng API và quan hệ happens-before thay vì trông chờ thử nghiệm ngẫu nhiên.

**Nhầm 8 — «Bất kỳ API nào dùng `StringBuilder` đều sai trong ứng dụng nhiều luồng».** Builder được sở hữu và sử dụng cục bộ bởi một luồng là trường hợp rất bình thường, kể cả trong server đa luồng.

**Nhầm 9 — «`StringBuffer` thay được mọi `Lock` hay cấu trúc concurrent».** Nó không cung cấp transaction đa đối tượng, hàng đợi message hay giao thức đặt thứ tự sự kiện.

**Nhầm 10 — «`StringBuffer` là immutable như `String`».** `StringBuffer` có thể sửa tại chỗ, vì thế phải cân nhắc ownership, đồng bộ và việc lộ tham chiếu ra ngoài.

## 8. Câu hỏi tự kiểm tra

### Câu 1: số ký tự cuối cùng

Bốn luồng, mỗi luồng append `"x"` một nghìn lần vào cùng `StringBuffer`; luồng chính chỉ đọc sau `join`. Với giả định không có thao tác xóa, độ dài mong đợi là bao nhiêu?

**Đáp án:** 4.000. Mỗi `append` được đồng bộ trên buffer; `join` giúp luồng chính đọc sau khi tất cả đã hoàn thành.

### Câu 2: vì sao vẫn cần `synchronized(shared)`?

```java
if (shared.length() < 10) {
    shared.append("x");
}
```

**Đáp án:** giữa `length()` và `append()`, luồng khác có thể append. Để duy trì giới hạn 10, phải khóa vùng đọc–kiểm tra–ghi như một thao tác nghiệp vụ.

### Câu 3: chia sẻ nguồn hay chia sẻ đích?

Luồng A gọi `target.append((CharSequence) source)` trong khi luồng B sửa `source` là một `StringBuilder`. Bản thân `target` là `StringBuffer` có giải quyết trọn vấn đề không?

**Đáp án:** Không. Khóa của buffer đích không tự đồng bộ các lần đọc nguồn với các lần ghi nguồn. Cần ownership rõ ràng, snapshot hoặc phối hợp khóa giữa các luồng dùng nguồn.

### Câu 4: thiết kế bản ghi nhiều thành phần

Nhiều luồng cần thêm các dòng `id=..., status=...` vào một buffer dùng chung mà mỗi dòng phải liền mạch. Có thể chọn giải pháp nào?

**Đáp án:** tạo toàn bộ dòng thành một `String` trong `StringBuilder` cục bộ rồi gọi một `shared.append(record)`, hoặc khóa cùng một buffer quanh toàn bộ các lần append của một dòng. Nếu cần giữ thứ tự giữa các bản ghi, phải có giao thức thứ tự riêng.

### Câu 5: nên chọn builder nào?

Một hàm chỉ xây dựng JSON đơn giản để trả về một `String`, mỗi lần gọi tạo builder mới và không để các luồng khác chạm vào builder. Cần dùng `StringBuffer` không?

**Đáp án:** Không nhất thiết. `StringBuilder` cục bộ là lựa chọn tự nhiên nếu không yêu cầu các thao tác đồng bộ trên cùng đối tượng. Dù dùng lớp nào, JSON thực tế cần cơ chế escaping và định dạng hợp lệ; nối chuỗi thủ công không tự giải quyết các quy tắc JSON.

## Kết luận

**Vai trò của `StringBuffer` là hỗ trợ sửa một dãy ký tự dùng chung với các thao tác đã được đồng bộ ở mức đối tượng.** Nó phù hợp khi nhiều luồng thật sự cần tương tác với **cùng một buffer mutable**, nhưng không có nghĩa cả chuỗi thao tác đọc–kiểm tra–ghi được thực hiện nguyên tử, không bảo vệ tự động các nguồn mutable khác và không tạo ra thứ tự sự kiện tùy ý. Hãy xác định **dữ liệu nào được chia sẻ**, **khóa nào bảo vệ dữ liệu đó**, và **ranh giới nghiệp vụ nào cần nguyên tử**. Nếu văn bản chỉ được dựng cục bộ rồi truyền đi dưới dạng `String`, `StringBuilder` cục bộ cùng dữ liệu bất biến thường giúp thiết kế gọn hơn.