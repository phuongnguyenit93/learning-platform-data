# Hợp đồng của đối tượng là gì và vì sao mã gọi cần dựa vào hợp đồng?

## 1. Hiểu đúng về hợp đồng của đối tượng

Trong lập trình hướng đối tượng, **hợp đồng (contract)** là tập các cam kết về **hành vi có thể quan sát từ bên ngoài** của một đối tượng: người sử dụng được phép gọi gì, cần đáp ứng điều kiện nào, và có thể tin tưởng điều gì sau khi gọi. Hợp đồng có thể được mô tả bằng giao diện công khai, tài liệu API, đặc tả nghiệp vụ, kiểm thử và những quy tắc chung của Java.

Ví dụ, một đối tượng hàng đợi cam kết rằng phần tử được thêm trước sẽ được lấy ra trước (FIFO). Mã gọi có thể dựa vào thứ tự đó mà không cần biết bên trong đối tượng lưu dữ liệu bằng mảng, danh sách liên kết hay cấu trúc nào khác.

**Chữ ký phương thức chưa phải toàn bộ hợp đồng.** Hai lớp cùng có `String dequeue()` đều biên dịch được; nhưng nếu một lớp lấy phần tử cũ nhất và lớp kia lấy phần tử mới nhất thì chúng không thực hiện cùng một hợp đồng. Trình biên dịch giúp kiểm tra kiểu dữ liệu và khả năng truy cập, còn nhiều quy tắc hành vi phải được định nghĩa và kiểm chứng riêng.

Cũng cần phân biệt: “hợp đồng của đối tượng” theo nghĩa rộng là các cam kết hành vi của bất kỳ đối tượng nào; nó không chỉ nói về lớp `java.lang.Object` hay riêng `equals()`/`hashCode()`.

## 2. Một hợp đồng thường chứa những gì?

| Thành phần | Nội dung cần xác định | Ví dụ với hàng đợi |
| --- | --- | --- |
| Thao tác công khai | Đối tượng cho phép thực hiện việc gì? | `enqueue`, `dequeue`, `size` |
| Tiền điều kiện (precondition) | Mã gọi phải bảo đảm điều gì trước khi gọi? | Công việc thêm vào không được `null` hoặc chuỗi trắng |
| Hậu điều kiện (postcondition) | Nếu thao tác thành công, kết quả hoặc trạng thái phải thế nào? | `dequeue` trả về công việc cũ nhất và giảm kích thước đi 1 |
| Bất biến (invariant) | Điều gì luôn đúng ở trạng thái hợp lệ của đối tượng? | `size() >= 0`; các công việc đang chờ tuân theo FIFO |
| Xử lý trường hợp lỗi | Khi đầu vào không hợp lệ hoặc thiếu dữ liệu sẽ xảy ra gì? | Lấy từ hàng đợi rỗng ném `NoSuchElementException` |
| Đặc tính được bảo đảm khác | Khả năng thay đổi, thứ tự, tính nhất quán, luồng, v.v. | Chỉ được xem là thread-safe nếu hợp đồng có cam kết rõ |

Không phải API nào cũng cần ghi từng mục dưới dạng trang trọng. Tuy vậy, **những gì ảnh hưởng đến cách dùng đúng phải đủ rõ để người gọi không phải đoán**.

Ba ranh giới trách nhiệm quan trọng:

- **Người gọi** tuân thủ tiền điều kiện đã công bố: chẳng hạn không truyền công việc trống.
- **Đối tượng thực thi** bảo đảm hậu điều kiện, bất biến và cách báo lỗi đã hứa khi được sử dụng hợp lệ.
- **Tài liệu hợp đồng** phải nêu rõ các trường hợp đặc biệt: giá trị `null`, bộ sưu tập rỗng, thao tác thất bại, giới hạn dữ liệu hoặc khả năng sử dụng đồng thời.

Nếu hợp đồng không hứa điều gì, người gọi không nên suy ra cam kết đó chỉ vì phiên bản hiện tại tình cờ hoạt động như vậy.

## 3. Vì sao mã gọi phải dựa vào hợp đồng?

**Tách nhu cầu sử dụng khỏi cách cài đặt.** Mã gọi chỉ cần biết `dequeue()` trả về công việc cũ nhất. Khi đổi cấu trúc lưu trữ, mã gọi không phải sửa nếu cam kết này vẫn giữ nguyên. Đây là cơ sở của tính đóng gói và thiết kế theo abstraction.

**Cho phép thay thế implementation.** Một đối tượng khác có thể được dùng thay nếu nó thỏa cùng những yêu cầu mà người gọi đang dựa vào. Tính thay thế này là ý tưởng trung tâm của nguyên lý Liskov Substitution: chỉ trùng chữ ký phương thức là chưa đủ; kết quả, điều kiện gọi và hành vi lỗi cũng phải tương thích.

**Giảm sự phụ thuộc dễ vỡ.** Nếu mã gọi đọc trực tiếp trường nội bộ, giả định một lớp luôn dùng `ArrayDeque`, hoặc dựa vào thứ tự không được cam kết, một lần tối ưu nội bộ có thể làm chương trình sai dù API công khai không đổi.

**Giúp xác định lỗi và viết kiểm thử.** Khi đặc tả nói “lấy ra theo FIFO”, ta có thể kiểm thử FIFO trên mọi implementation. Nếu kết quả khác, lỗi nằm ở bên vi phạm hợp đồng; không cần suy đoán dựa trên chi tiết nội bộ.

**Giúp API dễ học và dễ bảo trì.** Người mới sử dụng biết rõ đầu vào hợp lệ, kết quả mong đợi và ngoại lệ cần xử lý. Nhóm phát triển biết những hành vi nào phải giữ khi refactor.

## 4. Ví dụ Java 17+: người gọi chỉ biết hợp đồng hàng đợi

Giả sử hệ thống xử lý công việc theo thứ tự được gửi đến. Ta công bố hợp đồng `TaskQueue`:

1. `enqueue(task)` chỉ chấp nhận chuỗi khác `null` và không trắng; gọi thành công thêm công việc vào cuối hàng.
2. `dequeue()` lấy và xóa công việc cũ nhất; nếu rỗng, ném `NoSuchElementException` và không đổi trạng thái.
3. `size()` cho biết số công việc đang chờ; số này không âm.
4. Ví dụ không cam kết an toàn khi nhiều luồng truy cập đồng thời.

Tạo tệp `ContractDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.NoSuchElementException;

public final class ContractDemo {
    interface TaskQueue {
        void enqueue(String task);
        String dequeue();
        int size();
    }

    static final class InMemoryTaskQueue implements TaskQueue {
        private final Deque<String> tasks = new ArrayDeque<>();

        @Override
        public void enqueue(String task) {
            if (task == null || task.isBlank()) {
                throw new IllegalArgumentException("task must not be blank");
            }
            tasks.addLast(task);
        }

        @Override
        public String dequeue() {
            return tasks.removeFirst();
        }

        @Override
        public int size() {
            return tasks.size();
        }
    }

    static void process(TaskQueue queue) {
        queue.enqueue("build");
        queue.enqueue("test");
        System.out.println(queue.dequeue());
        System.out.println(queue.dequeue());
        System.out.println(queue.size());
        try {
            queue.dequeue();
        } catch (NoSuchElementException ex) {
            System.out.println("empty");
        }
    }

    public static void main(String[] args) {
        process(new InMemoryTaskQueue());
    }
}
```

Biên dịch và chạy:

```bash
javac ContractDemo.java
java ContractDemo
```

Kết quả chuẩn:

```text
build
test
0
empty
```

**Giải thích các cam kết được thực hiện:**

- `process` nhận kiểu `TaskQueue`, chỉ gọi các thao tác được công bố. Trong ví dụ, nó nhận một hàng đợi mới, ban đầu rỗng.
- `addLast` và `removeFirst` thực hiện FIFO; mã gọi không phải biết đến `Deque`.
- Kiểm tra đầu vào diễn ra trước khi thêm; `enqueue(null)` hoặc `enqueue("   ")` ném `IllegalArgumentException` và không thêm công việc.
- `removeFirst()` của `ArrayDeque` ném `NoSuchElementException` khi rỗng mà không xóa gì; `process` có thể xử lý trường hợp này theo hợp đồng.
- `size()` đọc đúng số phần tử hiện có. Nếu thay `ArrayDeque` bằng một cấu trúc khác, implementation mới vẫn phải giữ FIFO, điều kiện đầu vào, các ngoại lệ và ý nghĩa của `size`.

Mã phía ngoài sẽ gặp lỗi logic nếu một implementation mới âm thầm chuyển sang LIFO, dù tên phương thức và kiểu trả về không đổi. Đây chính là lý do mã gọi phụ thuộc vào **hành vi đã cam kết**, không phải chỉ vào interface.

## 5. Các hợp đồng quen thuộc ngay trong Java

Java có nhiều ví dụ cho thấy hợp đồng đi xa hơn chữ ký phương thức:

- **`Object.equals(Object)`:** nếu dùng để định nghĩa sự bằng nhau, phương thức phải tuân theo các tính chất phản xạ, đối xứng, bắc cầu, nhất quán (khi thông tin liên quan không đổi), và `x.equals(null)` phải là `false` với `x` khác `null`.
- **`Object.hashCode()`:** hai đối tượng bằng nhau theo `equals` phải có cùng mã băm; hai đối tượng có cùng mã băm không nhất thiết bằng nhau. Vì vậy, `HashMap`/`HashSet` có thể dựa vào cả hai hợp đồng.
- **`Comparable.compareTo`:** bên gọi dùng dấu âm, 0, dương để suy ra thứ tự; implementation phải bảo đảm quy tắc so sánh nhất quán được công bố. Sắp xếp có thể sai hoặc ném ngoại lệ nếu comparator vi phạm hợp đồng.
- **`List.get(index)`:** người gọi dựa vào chỉ số, thứ tự và ngoại lệ cho chỉ số ngoài phạm vi, không phải vào việc danh sách lưu phần tử trong mảng hay nút liên kết.

Các hợp đồng này vẫn có những giới hạn cần đọc trong tài liệu API cụ thể. Ví dụ, `toString()` **không** mặc định bảo đảm chuỗi có định dạng ổn định để máy khác phân tích; nếu cần định dạng trao đổi dữ liệu, hãy dùng một đặc tả định dạng rõ ràng.

## 6. Cách đọc và thiết kế hợp đồng trong thực tế

1. **Nêu hành vi quan sát được.** Với mỗi phương thức, hỏi: đầu vào hợp lệ là gì, kết quả có ý nghĩa gì, và trạng thái nào được phép thay đổi?
2. **Làm rõ tình huống biên.** Đặc tả `null`, giá trị rỗng, số âm, phần tử không tồn tại, tràn số và lỗi; không để người gọi tự đoán.
3. **Ghi hợp đồng ở nơi người dùng API nhìn thấy.** Trong Java, dùng tên kiểu và phương thức rõ ràng, JavaDoc (`@param`, `@return`, `@throws`), interface và tài liệu mô tả bất biến. Annotation kiểm tra null hoặc validation có thể hỗ trợ, nhưng không tự diễn đạt mọi quy tắc hành vi.
4. **Viết kiểm thử theo hợp đồng.** Ví dụ: thêm A rồi B phải lấy A rồi B; lấy từ hàng đợi rỗng phải ném ngoại lệ đã nêu; đầu vào không hợp lệ không làm thay đổi kích thước. Chạy cùng bộ kiểm thử cho mọi implementation.
5. **Kiểm tra khả năng thay thế.** Khi tạo subclass hay implementation mới, đừng tùy tiện đòi hỏi tiền điều kiện mạnh hơn, trả kết quả yếu hơn, hoặc thay quy tắc lỗi mà bên gọi đang phụ thuộc.
6. **Phân biệt bảo đảm với chi tiết cài đặt.** FIFO là hợp đồng trong ví dụ; sử dụng `ArrayDeque`, dung lượng bộ nhớ, thứ tự trường private hay dòng log nội bộ không phải cam kết cho mã gọi.

Một API tốt còn phải nói rõ mức độ an toàn luồng, việc lưu hay sao chép dữ liệu đầu vào, quyền sở hữu tài nguyên và chính sách thay đổi trạng thái **khi những yếu tố đó ảnh hưởng đến người sử dụng**. Không mặc định một object bất biến hoặc thread-safe chỉ vì nó có interface nhỏ.

## 7. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Có cùng interface là thay thế được.” | Còn phải giữ các quy tắc hành vi mà người gọi được quyền trông đợi. |
| “Chạy thử một lần thấy đúng thì đó là hợp đồng.” | Một kết quả quan sát được chưa chứng minh lời bảo đảm lâu dài; hãy dựa vào đặc tả và kiểm thử. |
| “Precondition bị vi phạm nhưng object vẫn phải xử lý thành công.” | Người gọi chịu trách nhiệm với tiền điều kiện; hành vi khi vi phạm cần xem đặc tả cụ thể. |
| “Có `equals()` là đã có toàn bộ object contract.” | `equals`/`hashCode` chỉ là những hợp đồng cụ thể trong số nhiều hợp đồng hành vi. |
| “Chỉ cần trả đúng dữ liệu, ngoại lệ nào cũng được.” | Loại lỗi, thời điểm ném và việc trạng thái có bị thay đổi hay không cũng có thể là phần quan trọng của hợp đồng. |

**Tự kiểm tra:** Nếu thay implementation hàng đợi nhưng `dequeue()` lấy phần tử cuối cùng trước, mã Java có còn biên dịch không? Có thể có. Mã gọi có còn đúng không? Không, vì implementation mới đã vi phạm cam kết FIFO. Nếu thay cấu trúc lưu trữ nhưng mọi cam kết công khai vẫn đúng, mã gọi có cần biết việc thay đổi không? Không.

**Ghi nhớ:** Hợp đồng là ranh giới tin cậy giữa đối tượng và mã sử dụng nó. Đóng gói giúp giấu cách làm; hợp đồng cho biết điều gì vẫn phải đúng bất kể cách làm thay đổi.