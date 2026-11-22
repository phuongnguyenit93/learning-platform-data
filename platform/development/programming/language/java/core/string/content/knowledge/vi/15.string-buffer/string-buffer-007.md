# Chi phí đồng bộ và điều kiện thực sự cần StringBuffer

## 1. Mục tiêu và kết luận thực hành

`StringBuffer` là chuỗi ký tự **có thể thay đổi** và có cơ chế đồng bộ cho những thao tác cần thiết trên **cùng một đối tượng**. `StringBuilder` có API gần tương đương nhưng **không tự đồng bộ**. Vì vậy, khi tạo chuỗi trong một phương thức, trong một request, hoặc trong một tác vụ mà buffer chỉ do một luồng sở hữu, lựa chọn thông thường là `StringBuilder`. Chỉ cân nhắc `StringBuffer` khi thực sự có nhiều luồng truy cập và thay đổi **cùng một buffer**, cần bảo vệ tính nhất quán ở mức **từng lời gọi phương thức**, hoặc phải tương thích với API cũ dùng `StringBuffer`.

Điểm mấu chốt: “thread-safe” của `StringBuffer` **không** có nghĩa mọi chuỗi thao tác gồm nhiều lời gọi đều nguyên tử, không áp đặt thứ tự giữa các luồng, và không tự bảo vệ một `CharSequence` nguồn đang bị luồng khác sửa.

## 2. Đồng bộ của StringBuffer hoạt động như thế nào?

- Các phương thức cần bảo vệ trạng thái như `append(...)`, `insert(...)`, `delete(...)`, `setLength(...)` và nhiều thao tác đọc sử dụng đồng bộ trên đối tượng `StringBuffer` tương ứng. Các lần gọi trên **cùng đối tượng** được phối hợp bằng monitor, tránh ghi đè hoặc làm hỏng trạng thái nội bộ khi các luồng cùng thao tác đúng theo hợp đồng API.
- Khi một luồng thoát khỏi khối/phương thức `synchronized` và luồng khác sau đó lấy **cùng monitor**, Java Memory Model thiết lập quan hệ *happens-before* giữa lần mở khóa và lần khóa tiếp theo, nhờ đó các thay đổi được công bố phù hợp.
- Monitor là **theo đối tượng**, không phải khóa toàn cục cho mọi `StringBuffer`. Hai buffer độc lập không tranh chấp cùng khóa nội tại.
- Với `append("A")`, thao tác thêm chuỗi đó vào buffer được bảo vệ như một lời gọi. Nhưng `append("[")` rồi `append("A")` rồi `append("]")` là **ba** lời gọi; một luồng khác có thể xen thao tác của nó giữa các lời gọi ấy.
- Đồng bộ bảo vệ buffer **đích**, không mặc nhiên khóa dữ liệu nguồn. Ví dụ, khi `append(CharSequence source)` đọc một đối tượng nguồn có thể thay đổi và đang được chia sẻ, người gọi phải bảo đảm dữ liệu nguồn ổn định trong suốt lần đọc (chẳng hạn dùng `String` bất biến hoặc đồng bộ thích hợp).

### Mức độ bảo đảm cần phân biệt

| Tình huống | `StringBuffer` tự bảo đảm? | Giải thích |
| --- | --- | --- |
| Nhiều luồng gọi `append('x')` vào cùng buffer | Có, ở mức từng lời gọi | Trạng thái nội bộ không bị cập nhật đồng thời thiếu đồng bộ; thứ tự ký tự tùy lịch chạy |
| Hai lần `append` liên tiếp phải đi liền nhau | Không | Luồng khác có thể xen vào giữa |
| `if (buffer.length() == 0) buffer.append("init")` chỉ chạy một lần | Không | Đọc và ghi là hai thao tác riêng |
| Các luồng bắt buộc có thứ tự A trước B | Không | Cần cơ chế điều phối/thứ tự bên ngoài |
| Buffer nguồn khác đang bị sửa trong lúc `append(source)` | Không | Khóa trên đích không tự tạo snapshot ổn định của nguồn |
| Mỗi luồng làm việc với buffer riêng | Không cần đồng bộ giữa các buffer | `StringBuilder` thường phù hợp hơn |

## 3. Chi phí đồng bộ đến từ đâu?

Một lần gọi phương thức được đồng bộ có thêm công việc phối hợp khóa và các ràng buộc về bộ nhớ so với thao tác tương ứng không đồng bộ. Cần tách hai trường hợp:

1. **Không có tranh chấp khóa:** vẫn có chi phí biểu đạt và xử lý đồng bộ, nhưng HotSpot/JIT có thể tối ưu các khóa thích hợp (ví dụ khi chứng minh đối tượng không thoát khỏi phạm vi). Không thể kết luận mọi lần `append` đều chậm một lượng cố định; hiệu quả tùy JDK, mã và cách chạy.
2. **Có nhiều luồng tranh chấp cùng buffer:** tại một thời điểm chỉ một luồng giữ monitor cho phần việc được khóa. Các luồng khác phải chờ; việc chuyển quyền sở hữu khóa, đồng bộ bộ nhớ và điều phối luồng làm tăng độ trễ, hạn chế thông lượng và khả năng mở rộng. Với chuỗi nhiều lần `append` rất ngắn, chi phí tranh chấp có thể đáng kể so với công việc nối ký tự.

Ngoài khóa, cả `StringBuilder` và `StringBuffer` đều có thể phải mở rộng vùng chứa khi vượt `capacity()`. Việc cấp phát/sao chép lúc tăng dung lượng là **chi phí khác** với đồng bộ; đặt dung lượng ban đầu hợp lý có thể giúp cả hai. Đừng quy mọi chênh lệch thời gian hoặc bộ nhớ cho `synchronized`.

Không có một tỷ lệ kiểu “`StringBuffer` chậm gấp N lần” đúng cho mọi ứng dụng. JVM có warm-up, JIT, garbage collector, kích thước dữ liệu, mức tranh chấp và cách sử dụng khác nhau. Ngay cả phép thử chỉ có một luồng cũng không phản ánh chi phí khi nhiều luồng chung một đối tượng.

## 4. Khi nào thật sự nên chọn StringBuffer?

**Trường hợp hợp lý:**

- **Một đối tượng mutable phải được dùng chung:** có nhiều luồng cùng `append`/sửa trên một `StringBuffer`, và hợp đồng nghiệp vụ chỉ cần an toàn cho **từng lời gọi**, không yêu cầu các lời gọi liên tiếp luôn tạo thành một giao dịch.
- **API/thư viện hiện có yêu cầu `StringBuffer`:** cần giữ đúng kiểu tham số hoặc hợp đồng tương thích trong hệ thống cũ. Khi sửa thiết kế, kiểm tra lại nhu cầu chia sẻ và khả năng thay bằng `StringBuilder`.
- **Cần dùng chung buffer với thao tác tổng hợp được khóa ngoài:** `StringBuffer` vẫn sử dụng được, nhưng phải bọc toàn bộ chuỗi kiểm tra/ghi trong cùng một `synchronized (buffer)` nếu muốn nguyên tử ở cấp nghiệp vụ. Trong một thiết kế mới, cũng nên cân nhắc trạng thái được đóng gói với một khóa rõ ràng và `StringBuilder` bên trong.

**Thường không cần `StringBuffer`:**

- Ghép chuỗi trong vòng lặp/method chạy ở một luồng; mỗi request/tác vụ có buffer riêng.
- Nhiều luồng làm việc song song nhưng **mỗi luồng sở hữu buffer riêng**, sau đó chuyển kết quả `String` bất biến cho bộ phận tổng hợp.
- Các chuỗi ngắn có biểu thức `+` rõ ràng, hoặc nối theo quy ước bằng `String.join`/`StringJoiner`/`Collectors.joining`. Chọn API theo độ dễ đọc và đặc tính dữ liệu; đừng tự giả định mọi phép `+` tạo ra quá nhiều đối tượng.
- Nhiều luồng tạo các đoạn văn bản độc lập: dùng kết quả cục bộ và một cơ chế tập hợp/điều phối phù hợp, tránh ép mọi luồng tranh chấp một buffer chung chỉ để “thread-safe”.

### Quy tắc chọn nhanh

| Đặc điểm công việc | Lựa chọn thường hợp lý | Vì sao |
| --- | --- | --- |
| Ghép chuỗi biến đổi ở một luồng | `StringBuilder` | Không cần khóa cho buffer cục bộ |
| Chỉ cần chuỗi bất biến đã hoàn thiện | `String` | Dễ chia sẻ, không cần đồng bộ việc sửa |
| Nhiều luồng nối vào **cùng** mutable buffer, thao tác độc lập | `StringBuffer` | Đồng bộ từng thao tác |
| Nhiều luồng ghi một bản ghi phải liền mạch qua nhiều lời gọi | Một vùng khóa bao toàn bản ghi hoặc append cả bản ghi đã tạo sẵn bằng **một** lời gọi | `StringBuffer` đơn lẻ không làm nhiều lời gọi trở nên nguyên tử |
| Hệ thống legacy dùng chữ ký `StringBuffer` | `StringBuffer` tại ranh giới đó | Tuân thủ hợp đồng hiện có |
| Nhiều luồng tạo đoạn chuỗi riêng | `StringBuilder` cục bộ + tập hợp kết quả có điều phối | Giảm tranh chấp khóa chung |

## 5. Ví dụ Java 17: giảm số lượt vào monitor bằng cách gom từng lô

Nếu mỗi luồng thêm hàng trăm ký tự độc lập vào một buffer chung, gọi `append(char)` từng ký tự sẽ có nhiều lần đi qua monitor của `StringBuffer`. Một lựa chọn khác là mỗi luồng xây **một đoạn cục bộ** trong `StringBuilder` rồi append trọn đoạn qua một lời gọi. Cả hai đúng về nội dung, nhưng **số lời gọi trên buffer dùng chung khác nhau**.

Tạo tệp `StringBufferBatchAppendDemo.java`:

```java
public class StringBufferBatchAppendDemo {
    private static void fill(StringBuffer shared, boolean batch)
            throws InterruptedException {
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            final char symbol = (char) ('A' + i);
            workers[i] = new Thread(() -> {
                for (int group = 0; group < 10; group++) {
                    if (batch) {
                        StringBuilder local = new StringBuilder(25);
                        for (int j = 0; j < 25; j++) {
                            local.append(symbol);
                        }
                        shared.append(local.toString());
                    } else {
                        for (int j = 0; j < 25; j++) {
                            shared.append(symbol);
                        }
                    }
                }
            });
        }

        for (Thread worker : workers) worker.start();
        for (Thread worker : workers) worker.join();
    }

    private static boolean expectedCounts(StringBuffer buffer) {
        String text = buffer.toString();
        if (text.length() != 1_000) return false;
        for (char letter = 'A'; letter <= 'D'; letter++) {
            final char expected = letter;
            if (text.chars().filter(ch -> ch == expected).count() != 250) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) throws InterruptedException {
        StringBuffer single = new StringBuffer();
        StringBuffer batched = new StringBuffer();
        fill(single, false);
        fill(batched, true);

        System.out.println("single correct=" + expectedCounts(single));
        System.out.println("batched correct=" + expectedCounts(batched));
        System.out.println("single append calls=" + (4 * 10 * 25));
        System.out.println("batched append calls=" + (4 * 10));
    }
}
```

```bash
javac StringBufferBatchAppendDemo.java
java StringBufferBatchAppendDemo
```

Kết quả:

```text
single correct=true
batched correct=true
single append calls=1000
batched append calls=40
```

Mỗi luồng thêm 250 ký tự của riêng nó nên hai kết quả đều dài 1.000 code unit và có 250 ký tự `A`, `B`, `C`, `D`. Phiên bản gọi từng ký tự sử dụng 1.000 lời gọi `append` trên buffer chung; phiên bản theo lô chỉ dùng 40 lần. Nội dung các nhóm có thể được sắp xen kẽ theo lịch luồng nhưng mỗi `append(String)` vẫn thêm toàn bộ nhóm như một thao tác trên đích.

**Đây là phép đếm lời gọi API, không phải benchmark tốc độ.** Phiên bản theo lô cần thêm `StringBuilder` và tạo `String` cục bộ, có thể tăng chi phí cấp phát. Lợi ích thực tế còn phụ thuộc kích thước lô, số luồng, mức contention và GC. Nếu hiệu năng quan trọng, đo bằng JMH với tải phù hợp trước khi chọn.


## 6. Đo hiệu năng đúng cách trước khi tối ưu

Nếu hiệu năng thật sự là vấn đề, lập benchmark tái hiện cách ứng dụng sử dụng buffer:

1. Tách kịch bản **buffer riêng mỗi luồng** và **nhiều luồng chung một buffer**. Đây là hai bài toán khác nhau.
2. Với phương án cần so sánh, giữ logic tạo dữ liệu, kích thước chuỗi, số vòng, kích thước đầu vào và kết quả tương đương. Tránh tối ưu sai ngữ nghĩa chỉ để có con số đẹp.
3. Dùng **JMH** với warm-up, nhiều lần đo/fork và số luồng rõ ràng; kiểm tra kết quả được tiêu thụ để JIT không loại bỏ công việc. Đo cả throughput lẫn latency khi có contention.
4. Quan sát profiler/metric về thời gian chờ monitor, CPU, cấp phát và GC khi phù hợp; so sánh trên JDK/hardware gần môi trường chạy thật.
5. Nếu một buffer chung trở thành nút thắt, xem xét lại **thiết kế chia sẻ** trước khi thay một lớp bằng lớp khác. Thay `StringBuffer` chung thành `StringBuilder` chung mà không thêm đồng bộ là **sai về thread safety**.

Không dùng `System.nanoTime()` đo một vòng lặp đơn rồi kết luận kết quả đại diện cho hệ thống: warm-up, inlining, dead-code elimination và scheduler đều có thể làm phép đo sai lệch.

## 7. Những lỗi hiểu sai thường gặp

- **“Ứng dụng đa luồng nên mọi nối chuỗi phải là StringBuffer.”** Sai: điều quyết định là **cùng instance có bị truy cập đồng thời không**, chứ không phải ứng dụng có bao nhiêu thread.
- **“StringBuffer làm cả đoạn code thread-safe.”** Sai: nó chỉ bảo vệ hành vi từng thao tác theo hợp đồng của lớp. Quy tắc kiểm tra-rồi-ghi, nhiều bước cập nhật, hoặc quan hệ với dữ liệu khác vẫn phải đồng bộ riêng.
- **“Synchronized luôn khiến chương trình chậm nghiêm trọng.”** Sai: không có hệ số cố định; JIT có tối ưu và chi phí phụ thuộc tranh chấp. Tuy nhiên khóa trên tài nguyên chung vẫn có thể thành điểm nghẽn.
- **“Có thể thay StringBuffer chung bằng StringBuilder để tăng tốc.”** Sai nếu không thiết kế lại ownership/locking; `StringBuilder` không bảo đảm an toàn cho ghi đồng thời.
- **“StringBuffer tự khóa cả CharSequence nguồn.”** Sai: nó chỉ đồng bộ trên buffer đích; nguồn mutable được chia sẻ cần bảo vệ hoặc snapshot độc lập.
- **“Nếu hai luồng append thì ký tự chắc chắn theo thứ tự luồng tạo trước.”** Sai: thứ tự thực thi phụ thuộc scheduler và điều phối đồng bộ.

## 8. Checklist trước khi chọn lớp

Trước khi giữ hoặc tạo một `StringBuffer`, hãy tự trả lời: **(1)** Có nhiều luồng thực sự dùng chung *cùng instance* không? **(2)** Có ghi đồng thời không? **(3)** Mỗi lần gọi riêng đã đáp ứng tính nguyên tử của nghiệp vụ chưa? **(4)** Có thể tạo nội dung cục bộ rồi chia sẻ `String` bất biến không? **(5)** Có ràng buộc tương thích API không? **(6)** Đã đo thấy contention hoặc tác động hiệu năng đáng kể chưa?

Nếu chỉ cần ghép dữ liệu cục bộ, chọn `StringBuilder`. Nếu thật sự cần chia sẻ một buffer mutable với các thay đổi ở mức từng phương thức, `StringBuffer` là lựa chọn sẵn có. Nếu cần bất biến ở cấp nhiều thao tác hoặc thứ tự nghiệp vụ, phải thiết kế thêm cơ chế đồng bộ/điều phối, bất kể tên lớp là gì.

### Tài liệu tham khảo

- [Oracle Java SE 17 — StringBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuffer.html)
- [Oracle Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
