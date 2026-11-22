# Tại sao ArrayDeque không bảo đảm an toàn khi dùng chung giữa nhiều luồng

## 1. Từ hàng đợi hai đầu đến trạng thái dùng chung

`ArrayDeque<E>` là một hàng đợi hai đầu dựa trên mảng: có thể thêm, lấy hoặc xóa phần tử ở đầu và cuối. Nó phù hợp làm hàng đợi hoặc ngăn xếp trong một luồng. Vấn đề xuất hiện khi nhiều luồng cùng giữ tham chiếu đến **một đối tượng deque có thể thay đổi**.

An toàn luồng (thread safety) nghĩa là các thao tác đồng thời vẫn duy trì hợp đồng của cấu trúc dữ liệu và bảo đảm cần thiết về khả năng nhìn thấy dữ liệu. `ArrayDeque` không tự cung cấp điều đó. Tài liệu Java nêu rõ cần đồng bộ bên ngoài khi dùng chung giữa các luồng. Đây vẫn là đặc tính hiện hành, không phải hạn chế chỉ có ở Java 6. Xem [hợp đồng ArrayDeque của Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html).

Ví dụ thực tế: hai luồng nhận yêu cầu cùng thêm công việc vào một deque, còn luồng xử lý lấy việc ra. Nếu coi mọi lời gọi `addLast` và `pollFirst` như thao tác tự được bảo vệ, chương trình đã dựa vào một bảo đảm mà lớp này không có.

## 2. Một lời gọi phương thức chứa nhiều bước

Trong cách triển khai OpenJDK 21, deque giữ mảng chứa phần tử cùng chỉ số đầu và cuối. Thêm hoặc xóa cần phối hợp việc đọc chỉ số, truy cập ô mảng và cập nhật vị trí. Khi tăng sức chứa, còn phải thay mảng và sắp xếp lại dữ liệu. Những bước này không được bao bởi khóa nội bộ. Chi tiết có thể thay đổi giữa các bản JDK; không nên dựa vào tên trường hoặc công thức tăng kích thước để viết mã ứng dụng. Xem [mã nguồn ArrayDeque trong OpenJDK 21](https://raw.githubusercontent.com/openjdk/jdk21u/master/src/java.base/share/classes/java/util/ArrayDeque.java).

Để thấy nguyên nhân, tưởng tượng một hàng đợi vòng đơn giản thêm phần tử theo ba bước:

1. Đọc vị trí cuối.
2. Ghi phần tử vào ô ở vị trí đó.
3. Dịch vị trí cuối sang ô tiếp theo.

Đây là **mô hình giải thích**, không phải mã nguồn để tự cài đặt deque và không mô tả mọi cách xen kẽ của JVM.

| Thời điểm | Luồng A thêm X | Luồng B thêm Y |
| --- | --- | --- |
| 1 | Đọc vị trí cuối là 5 | |
| 2 | | Cũng đọc vị trí cuối là 5 |
| 3 | Ghi X vào ô 5 | |
| 4 | | Ghi Y vào ô 5 |
| 5 | Cập nhật vị trí cuối thành 6 | |
| 6 | | Cập nhật vị trí cuối thành 6 |

Hai lần thêm đã tranh chấp cùng một ô. Mô hình cho thấy vì sao **một phép gán đơn lẻ có thể nguyên tử nhưng cả thuật toán vẫn không nguyên tử**. Không được suy ra mọi lần chạy `ArrayDeque` thực tế đều mất đúng một phần tử theo bảng này.

Với ứng dụng, câu hỏi cần đặt ra là: “Ai bảo vệ toàn bộ trạng thái liên quan trong lúc một thao tác đang diễn ra?” Nếu câu trả lời là “không có cơ chế nào”, việc các phương thức ngắn hoặc thường chạy rất nhanh không giúp chúng an toàn.

## 3. Hai vấn đề khác nhau: xen kẽ thao tác và nhìn thấy dữ liệu

### Xen kẽ thao tác

Điều kiện tranh chấp (race condition) xuất hiện khi kết quả phụ thuộc vào thứ tự xen kẽ giữa các luồng mà chương trình chưa kiểm soát. Cả hai luồng có thể cùng quyết định dựa trên trạng thái đã cũ trước khi ghi kết quả.

Đặc biệt, một luồng thêm ở cuối và một luồng lấy ở đầu **vẫn chưa đủ để kết luận an toàn**. Chúng cùng làm việc trên một cấu trúc có các quan hệ nội bộ; trường hợp rỗng hoặc thay đổi sức chứa không thể được giải quyết chỉ bằng lập luận “khác đầu thì khác dữ liệu”.

### Nhìn thấy dữ liệu và quan hệ happens-before

Java Memory Model dùng quan hệ `happens-before` để quy định thứ tự và khả năng nhìn thấy các hành động giữa các luồng. Thoát khỏi một khối `synchronized` tạo quan hệ này với lần lấy **cùng khóa** về sau. Gọi `Thread.start()` và đợi luồng kết thúc bằng `join()` cũng có các bảo đảm công bố dữ liệu tương ứng. Xem [JLS, chương 17](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.5).

Không có giao thức đồng bộ thích hợp, một luồng đọc không có bảo đảm cần thiết để quan sát các thay đổi của luồng khác theo cách thuật toán yêu cầu. “Luồng kia chắc đã ghi xong từ lâu” không phải một quan hệ đồng bộ.

Những cách sau không tự sửa được vấn đề:

- `final Deque<Integer> q = new ArrayDeque<>();` ngăn gán lại biến `q`; nó không khóa các lần sửa deque.
- Khai báo tham chiếu là `volatile` không biến các thao tác sửa đối tượng mà nó trỏ tới thành thao tác có khóa.
- `Thread.sleep(...)` không thay cho giao thức đồng bộ.
- Chỉ khóa bên ghi, trong khi bên đọc gọi trực tiếp `size()`, `peekFirst()` hoặc duyệt deque, không tạo thành một giao thức thống nhất.
- Hai luồng dùng hai đối tượng khóa khác nhau không loại trừ lẫn nhau.

`volatile` có thể là một phần của thiết kế công bố dữ liệu đúng, nhưng không tự gộp chuỗi đọc–sửa–ghi thành một thao tác nguyên tử. Các bảo đảm của `start`, `join`, `volatile` và khóa được tóm tắt tại [java.util.concurrent: Memory Consistency Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html).

## 4. Kiểm tra rồi mới lấy: một lỗi ở cấp nghiệp vụ

Đoạn dưới là mã minh họa **không an toàn khi thiếu bảo vệ**, giả sử `q` là deque dùng chung:

```java
if (!q.isEmpty()) {
    Integer item = q.removeFirst();
    // Xu ly item.
}
```

Ngay sau khi luồng A kiểm tra “chưa rỗng”, luồng B có thể lấy phần tử cuối cùng. Khi A gọi `removeFirst()`, điều kiện vừa kiểm tra không còn đúng.

Nếu sử dụng một cấu trúc hỗ trợ truy cập đồng thời, thường nên dùng phép “lấy hoặc trả về rỗng”:

```java
Integer item = concurrentDeque.pollFirst();
if (item != null) {
    // Xu ly item.
}
```

Tuy nhiên, **đổi `removeFirst()` thành `pollFirst()` trên chính ArrayDeque chưa được đồng bộ không làm nó an toàn luồng**. Đổi phương thức chỉ đổi cách biểu diễn trường hợp rỗng. Muốn dùng `ArrayDeque` chung, vẫn cần khóa; muốn dùng deque đồng thời, phải chọn một triển khai phù hợp.

Ngoài ra, `null` từ `pollFirst()` chỉ cho biết không lấy được phần tử tại thời điểm thao tác. Nó không chứng minh các luồng sản xuất đã hoàn thành hoặc sẽ không thêm việc nữa. Cơ chế kết thúc công việc là một yêu cầu riêng.

## 5. Cách 1: giữ deque trong một luồng

Nếu mỗi tác vụ chỉ cần ngăn xếp để duyệt cây, phân tích biểu thức hoặc lưu công việc cục bộ, hãy tạo deque riêng trong tác vụ đó. Nhiều luồng có thể đồng thời dùng **các đối tượng ArrayDeque khác nhau** mà không chia sẻ trạng thái deque.

Biến cục bộ không tự bảo đảm cô lập: nếu truyền deque cho một tác vụ bất đồng bộ hoặc lưu nó vào nơi các luồng khác truy cập được, đối tượng đã thoát khỏi phạm vi riêng. Cần theo dõi đối tượng và quyền truy cập, không chỉ nhìn vị trí khai báo biến.

Một trường hợp khác là xây dựng deque, công bố an toàn cho các luồng đọc, rồi **không sửa nữa**. Khi đó phải bảo đảm không còn đường ghi nào và các đối tượng phần tử cũng được xử lý đúng. Nếu nhu cầu thực sự là dữ liệu chỉ đọc, có thể cân nhắc biểu diễn bất biến để tránh vô tình sửa về sau.

## 6. Cách 2: một khóa bảo vệ mọi đường truy cập

Khi thật sự cần dùng chung `ArrayDeque`, có thể đặt nó trong một lớp sở hữu khóa riêng. Mọi lần thêm, xóa, đọc, lấy kích thước và tạo bản sao đều phải tuân thủ cùng giao thức. Không trả deque gốc hoặc iterator của nó ra ngoài.

Ví dụ đầy đủ dưới đây chạy trên Java 17+. Hai luồng thêm các số từ 1 đến 2.000. Luồng chính đợi chúng hoàn thành, rồi lấy hết các số để kiểm tra số lượng và tổng. Chương trình không giả định thứ tự xen kẽ của hai luồng.

Tệp `LockedArrayDequeDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;

public class LockedArrayDequeDemo {
    private static final class LockedDeque {
        private final Object lock = new Object();
        private final Deque<Integer> deque = new ArrayDeque<>();

        void addLast(int value) {
            synchronized (lock) {
                deque.addLast(value);
            }
        }

        Integer pollFirst() {
            synchronized (lock) {
                return deque.pollFirst();
            }
        }

        int size() {
            synchronized (lock) {
                return deque.size();
            }
        }
    }

    private static void addRange(LockedDeque deque, int first, int last) {
        for (int i = first; i <= last; i++) {
            deque.addLast(i);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        LockedDeque deque = new LockedDeque();

        Thread a = new Thread(() -> addRange(deque, 1, 1000));
        Thread b = new Thread(() -> addRange(deque, 1001, 2000));

        a.start();
        b.start();
        a.join();
        b.join();

        int count = 0;
        long sum = 0;
        Integer value;
        while ((value = deque.pollFirst()) != null) {
            count++;
            sum += value;
        }

        System.out.println("count=" + count);
        System.out.println("sum=" + sum);
        System.out.println("remaining=" + deque.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 LockedArrayDequeDemo.java
java LockedArrayDequeDemo
```

Kết quả:

```text
count=2000
sum=2001000
remaining=0
```

Khóa bảo vệ hai luồng ghi trong lúc chúng chạy. `join()` giúp luồng chính biết giai đoạn sản xuất đã kết thúc trước khi lấy hết dữ liệu. Chỉ thêm `join()` vào một phiên bản ghi không khóa sẽ không sửa những cập nhật đã tranh chấp trước đó.

Ví dụ sử dụng các giá trị `Integer` bất biến. Nếu phần tử là đối tượng có trạng thái thay đổi, khóa bảo vệ deque không tự bảo vệ mọi lần sửa đối tượng đó ở bên ngoài.

Nếu một quy tắc cần nhiều thao tác, chẳng hạn “chỉ thêm khi số lượng nhỏ hơn giới hạn”, hãy đặt **cả kiểm tra và thêm** trong một lần giữ khóa. Hai phương thức riêng đều có khóa nhưng gọi nối tiếp từ bên ngoài vẫn cho phép luồng khác chen vào giữa chúng.

Không giữ khóa trong lúc xử lý công việc lâu hoặc gọi mã ngoài không kiểm soát. Thông thường, lấy phần tử trong khóa rồi xử lý nó sau khi đã nhả khóa.

## 7. Duyệt deque cũng thuộc phạm vi bảo vệ

`ConcurrentModificationException` không phải công cụ khóa. Iterator của `ArrayDeque` phát hiện thay đổi trên cơ sở nỗ lực tốt nhất; việc không phát sinh ngoại lệ không chứng minh chương trình an toàn. Không dùng `catch` ngoại lệ rồi thử lại làm cơ chế đồng bộ. Xem [quy định về iterator của ArrayDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html).

Có hai hướng thiết kế với deque được bảo vệ bằng khóa:

- Giữ cùng khóa trong toàn bộ quá trình tạo và sử dụng iterator. Các đường sửa khác cũng phải dùng khóa đó.
- Giữ khóa để sao chép dữ liệu sang danh sách riêng, nhả khóa rồi xử lý bản sao.

Hướng sao chép giảm thời gian giữ khóa nếu phần xử lý chậm. Bản sao cấu trúc thường chỉ sao chép tham chiếu phần tử; nó không làm các đối tượng phần tử trở nên bất biến.

Đặc biệt, lấy iterator trong khóa rồi trả nó cho nơi gọi sử dụng sau khi khóa đã nhả không bảo vệ được quá trình duyệt.

## 8. Cách 3: chọn deque được thiết kế cho truy cập đồng thời

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Ngăn xếp/hàng đợi riêng của một tác vụ | `ArrayDeque` |
| Cần phối hợp deque với một quy tắc nhiều bước bằng cùng khóa | Lớp bao `ArrayDeque` với khóa riêng |
| Nhiều luồng thêm/lấy, không cần chờ có phần tử | `ConcurrentLinkedDeque` |
| Luồng tiêu thụ cần chờ việc hoặc bên sản xuất cần chờ chỗ trống | `LinkedBlockingDeque`, thường đặt sức chứa rõ ràng |

### ConcurrentLinkedDeque

Lớp này hỗ trợ thêm, lấy và truy cập đồng thời. Iterator có tính nhất quán yếu: có thể duyệt trong khi deque thay đổi, không phải ảnh chụp cố định. `size()` cần duyệt và có thể không phản ánh một số lượng ổn định nếu có sửa đổi đồng thời. Các thao tác hàng loạt không được bảo đảm nguyên tử như một giao dịch. Xem [ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html).

Mã minh họa thao tác, không phải chương trình độc lập:

```java
Deque<String> jobs = new java.util.concurrent.ConcurrentLinkedDeque<>();
jobs.addLast("job-A");

String job = jobs.pollFirst();
if (job != null) {
    // Xu ly cong viec da lay duoc.
}
```

Không dùng `size() < limit` rồi `addLast(...)` để tạo giới hạn cứng cho deque này. Dù từng thao tác hỗ trợ truy cập đồng thời, chuỗi quyết định của ứng dụng vẫn cần cơ chế phối hợp riêng.

### LinkedBlockingDeque

Ví dụ khai báo `new LinkedBlockingDeque<String>(100)` tạo deque có sức chứa 100. `putLast(...)` có thể chờ chỗ trống; `takeFirst()` có thể chờ phần tử. Các thao tác chờ có thể bị ngắt bằng `InterruptedException`; ứng dụng phải có chính sách xử lý ngắt và kết thúc công việc. Xem [BlockingDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

Sức chứa rõ ràng hữu ích khi cần hạn chế lượng công việc đang chờ. Constructor không truyền sức chứa của `LinkedBlockingDeque` dùng giới hạn `Integer.MAX_VALUE`, không phải giới hạn thực tế nhỏ phù hợp với mọi ứng dụng. Xem [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

Đổi cấu trúc dữ liệu giải quyết phần hợp đồng đồng thời của cấu trúc. Nó không tự quyết định thay ứng dụng về thứ tự nghiệp vụ, số tác vụ phải xử lý, tín hiệu kết thúc hoặc cách phục hồi khi xử lý thất bại.

## 9. Tự kiểm tra cách thiết kế

Trước khi dùng một deque trong mã nhiều luồng, hãy trả lời:

1. Có những luồng nào giữ được tham chiếu đến cùng deque?
2. Ai có quyền sửa và các đường đọc có dùng cùng giao thức không?
3. Quy tắc nghiệp vụ gồm một thao tác hay nhiều thao tác cần nguyên tử?
4. Nếu lấy về `null`, nghĩa là tạm hết việc hay toàn hệ thống đã hoàn thành?
5. Iterator hoặc đối tượng phần tử có thoát ra ngoài vùng bảo vệ không?

Bài tập: trong ví dụ có khóa, thay `LockedDeque` bằng deque hỗ trợ truy cập đồng thời nhưng giữ nguyên cách chia khoảng số và đợi hai luồng kết thúc. Giải thích vì sao có thể bỏ khóa quanh từng lần thêm/lấy, đồng thời vì sao vẫn cần biết giai đoạn sản xuất đã kết thúc trước khi kết luận đã lấy hết dữ liệu.

Không dùng một lần chạy “đúng kết quả” của phiên bản thiếu đồng bộ làm bằng chứng. Lỗi tranh chấp phụ thuộc lịch chạy; kiểm thử không quan sát được lỗi không bổ sung bảo đảm mà hợp đồng và thiết kế đang thiếu.
