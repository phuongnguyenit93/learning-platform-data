# Phân biệt dữ liệu lớp được chia sẻ với trạng thái đối tượng ứng dụng

## 1. “Chia sẻ” phần nào, giữa những bên nào?

Khi nghe JVM có thể chia sẻ dữ liệu lớp để giảm bộ nhớ và tăng tốc khởi động, rất dễ hiểu nhầm rằng các đối tượng ứng dụng cũng trở thành dữ liệu dùng chung giữa nhiều tiến trình Java.

Cần tách hai câu hỏi:

1. **JVM biết gì về một lớp để thực thi mã?** Ví dụ: cấu trúc lớp, phương thức và những thông tin nội bộ dùng khi nạp lớp.
2. **Ứng dụng đang lưu giá trị gì khi chạy?** Ví dụ: danh sách món hàng trong một giỏ, bộ đếm yêu cầu, trạng thái đăng nhập hoặc cache đã tích lũy.

Dữ liệu lớp phục vụ việc hiểu và thực thi chương trình. Trạng thái ứng dụng là các giá trị thay đổi theo công việc của từng phiên chạy.

Trong HotSpot, **Class Data Sharing (CDS)** cho phép tái sử dụng dữ liệu lớp được chuẩn bị trước trong archive. Các vùng phù hợp có thể được ánh xạ để nhiều tiến trình dùng chung các trang bộ nhớ chỉ đọc. Điều này giúp giảm công việc nạp lớp và bộ nhớ lặp lại. Nó không tự tạo một kho trạng thái ứng dụng có thể ghi chung. [Hướng dẫn CDS](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html)

## 2. Ba loại dữ liệu cần phân biệt

| Loại | Ví dụ | Phạm vi cần hiểu |
|---|---|---|
| Dữ liệu mô tả lớp | Tên lớp, mô tả phương thức, dữ liệu JVM dùng cho việc nạp/thực thi lớp | Có thể có phần được tối ưu hoặc lưu trong archive theo triển khai |
| Trạng thái của từng đối tượng | Danh sách món hàng của giỏ A, số dư của tài khoản B | Thuộc đối tượng cụ thể mà chương trình tạo và giữ tham chiếu |
| Trạng thái static | Bộ đếm hoặc map static của một lớp | Gắn với lớp đã được định nghĩa trong JVM; không tự dùng chung giữa các JVM |

Ví dụ, hai đối tượng `Cart` có thể dùng cùng định nghĩa lớp và cùng mã phương thức `add`, nhưng mỗi đối tượng vẫn có danh sách món hàng riêng. Không cần nhân bản toàn bộ mã phương thức cho từng giỏ hàng để giữ được trạng thái riêng đó.

Ngược lại, một map static có thể được nhiều phần của cùng ứng dụng truy cập. Nó vẫn là trạng thái có thể thay đổi, không biến thành “metadata chỉ đọc” chỉ vì được khai báo trong một lớp.

Ở mức mô hình JVM, heap là vùng cấp phát cho các class instance và array; method area chứa các cấu trúc theo lớp. Đặc tả không buộc mọi triển khai phải dùng cùng cách bố trí vật lý, vì vậy không suy ra vị trí byte chính xác của một field chỉ từ sơ đồ học tập. [JVMS: vùng dữ liệu khi chạy](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-2.html#jvms-2.5)

## 3. Bốn ranh giới thường bị nhầm

### 3.1. Hai đối tượng của cùng lớp

Hai lần `new Cart()` tạo hai đối tượng riêng. Nếu constructor tạo danh sách riêng cho mỗi đối tượng, thêm phần tử vào danh sách của giỏ thứ nhất không tự thêm vào giỏ thứ hai.

Tính độc lập này phụ thuộc cách chương trình giữ tham chiếu. Nếu cả hai đối tượng cố ý được truyền cùng một danh sách thì chúng sẽ dùng chung danh sách đó; nguyên nhân là thiết kế tham chiếu của ứng dụng, không phải CDS.

### 3.2. Nhiều luồng trong cùng JVM

Các luồng có thể truy cập cùng một đối tượng khi chương trình truyền/chia sẻ tham chiếu cho chúng. Heap của một JVM có thể được các luồng trong JVM đó sử dụng.

Điều này không tự bảo đảm an toàn luồng. Nếu nhiều luồng cùng sửa một danh sách hoặc bộ đếm, phải dùng cơ chế đồng thời phù hợp. Bật CDS không sửa được race condition hoặc vấn đề hiển thị dữ liệu giữa các luồng.

### 3.3. Hai JVM dùng cùng JAR hoặc cùng archive

Hai JVM có thể nạp cùng lớp từ cùng artifact và cùng hưởng lợi từ archive. Tuy vậy, map cache, biến static mutable, giỏ hàng và phiên người dùng của mỗi JVM không tự đồng bộ với nhau.

JVM A thêm sản phẩm vào giỏ không làm JVM B thấy món đó. Nếu ứng dụng cần chia sẻ dữ liệu giữa tiến trình, phải có một cơ chế giao tiếp/lưu trữ được thiết kế cho mục đích đó.

### 3.4. Cùng tên lớp nhưng khác class loader

Ngay trong cùng một JVM, không coi chuỗi tên lớp là toàn bộ danh tính của kiểu. JVM nhận diện một lớp thông thường qua tên nhị phân và class loader định nghĩa nó.

Hai loader định nghĩa riêng cùng tên lớp có thể tạo ra hai kiểu khác nhau, với trạng thái static riêng. CDS không xóa ranh giới class loader đó. [JVMS: tạo và nạp lớp](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3)

## 4. static và final không có nghĩa là dữ liệu toàn cục giữa các tiến trình

### static: thuộc về lớp đã được định nghĩa

Một field static không được tạo lại cho mỗi instance. Trong một lớp cụ thể của JVM, các instance liên quan có thể quan sát cùng field static đó.

Ví dụ `static int created` đếm số đối tượng Cart đã tạo trong lớp/phiên chạy hiện tại. Nó không phải bộ đếm dùng chung cho mọi tiến trình đang chạy tệp Cart.class. [JLS: static field](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.3.1.1)

### final: giới hạn phép gán, không tự làm đối tượng bất biến

Xét khai báo:

~~~java
private final List<String> items = new ArrayList<>();
~~~

Đây là một field minh họa bên trong lớp, cần import List và ArrayList. `final` ngăn field trỏ sang một danh sách khác sau khi đã được gán hợp lệ. Nó không ngăn các phần tử của danh sách thay đổi.

Tương tự, `static final Map<...>` không tự là map bất biến, không tự an toàn luồng và không trở thành bộ nhớ ghi chung giữa các JVM. Phải đọc cả loại đối tượng và những phương thức có thể thay đổi nó.

### Hằng số và literal không phải phiên dữ liệu nghiệp vụ

String literal hay giá trị hằng có thể được JVM xử lý tối ưu. Đừng dùng các trường hợp này để suy ra mọi đối tượng đều được lưu chung, hoặc coi các tham chiếu ở hai tiến trình như có thể đem so sánh bằng `==` trong cùng một biểu thức Java.

## 5. Ví dụ Java 17+: chung lớp, riêng đối tượng, static theo phiên JVM

Chương trình tạo hai giỏ hàng, thêm một món vào giỏ thứ nhất và theo dõi số giỏ đã tạo.

Lưu thành `StateBoundaryDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StateBoundaryDemo {
    static final class Cart {
        private static int created;

        static {
            System.out.println("[init] Cart");
        }

        private final List<String> items = new ArrayList<>();

        Cart() {
            created++;
        }

        void add(String item) {
            items.add(item);
        }

        int size() {
            return items.size();
        }

        static int createdCount() {
            return created;
        }
    }

    public static void main(String[] args) {
        Cart first = new Cart();
        Cart second = new Cart();
        first.add("book");

        System.out.println("same.class="
                + (first.getClass() == second.getClass()));
        System.out.println("first.size=" + first.size());
        System.out.println("second.size=" + second.size());
        System.out.println("created.in.this.jvm=" + Cart.createdCount());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~shell
javac StateBoundaryDemo.java
java StateBoundaryDemo
~~~

Stdout đã kiểm chứng trên OpenJDK 24:

~~~text
[init] Cart
same.class=true
first.size=1
second.size=0
created.in.this.jvm=2
~~~

Đọc từng dòng:

- `[init] Cart`: static initializer của Cart chạy khi lớp được khởi tạo trong phiên này.
- `same.class=true`: hai đối tượng có cùng đối tượng Class trong JVM của ví dụ. Điều này thể hiện cùng lớp, không chứng minh CDS đang hoạt động.
- `first.size=1`, `second.size=0`: hai đối tượng giữ hai danh sách riêng.
- `created.in.this.jvm=2`: field static được hai lần constructor cùng cập nhật trong phiên JVM này.

Chạy lại cùng lệnh `java StateBoundaryDemo` sẽ khởi tạo một JVM mới. Kết quả vẫn bắt đầu từ hai đối tượng của lần chạy mới, không thành 4 chỉ vì lần chạy trước đã tạo hai giỏ.

Static initializer và constructor vẫn có vai trò theo ngữ nghĩa Java. Việc tối ưu dữ liệu lớp không có nghĩa chương trình tùy ý bỏ qua mã khởi tạo ứng dụng. [JLS: khởi tạo lớp và đối tượng](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4)

Đây là thí nghiệm một luồng. Phép tăng `created++` trong ví dụ không được thiết kế làm bộ đếm an toàn cho nhiều luồng; mục tiêu đang kiểm tra là phạm vi của trạng thái.

## 6. So sánh với CDS bật tự động và CDS tắt

Trên HotSpot hỗ trợ CDS, chạy hai tiến trình riêng:

~~~shell
java -Xshare:auto StateBoundaryDemo
java -Xshare:off StateBoundaryDemo
~~~

Trong môi trường OpenJDK 24 đã kiểm chứng, **mỗi lệnh** đều in:

~~~text
[init] Cart
same.class=true
first.size=1
second.size=0
created.in.this.jvm=2
~~~

Kết quả nghiệp vụ của ví dụ không đổi. `-Xshare:auto` cho phép dùng archive khi phù hợp; `-Xshare:off` tắt CDS cho lần chạy đó.

Các lệnh này không tự tạo archive riêng cho Cart và không chứng minh Cart nằm trong archive mặc định của JDK. Chúng giúp đối chiếu rằng chính sách dùng archive của JVM không biến trạng thái giỏ hàng thành dữ liệu tồn tại chung giữa những lần chạy.

Muốn kiểm tra nguồn nạp lớp trên HotSpot, có thể thêm log:

~~~shell
java -Xshare:auto -Xlog:class+load=info:file=class-load.log StateBoundaryDemo
~~~

Sau khi chạy, đọc tệp log và tìm những dòng có nguồn `shared objects file`. Trong lần kiểm chứng, log có các dòng:

~~~text
[0.015s][info][class,load] java.lang.Object source: shared objects file
[0.015s][info][class,load] java.lang.String source: shared objects file
~~~

Mốc thời gian và danh sách lớp có thể khác theo phiên bản, phân phối JDK và môi trường. Đây là bằng chứng **các lớp JDK được nêu** đến từ archive trong lần chạy đó, không phải bằng chứng toàn bộ lớp ứng dụng hay các Cart instance được chia sẻ.

Nếu không thấy dòng mong đợi, kiểm tra khả năng dùng archive và cấu hình JVM. Không kết luận các đối tượng ứng dụng đã bị dùng chung chỉ từ một số bộ nhớ giảm hoặc một lần khởi động nhanh hơn.

## 7. CDS archive khác kho trạng thái và bản chụp tiến trình

Một archive giúp JVM tái sử dụng dữ liệu đã chuẩn bị cho việc thực thi. Nó không tự đóng vai trò:

- Cơ sở dữ liệu lưu giỏ hàng sau khi tiến trình dừng.
- Cache ghi chung mà các instance ứng dụng cùng cập nhật.
- Bộ đồng bộ static field giữa các máy hoặc tiến trình.
- Bản chụp toàn bộ mọi kết nối, luồng và trạng thái nghiệp vụ để tiếp tục y nguyên phiên trước.

AppCDS mở rộng phạm vi tới các lớp ứng dụng được chọn. Việc một lớp ứng dụng được đưa vào archive không có nghĩa các instance phát sinh khi xử lý yêu cầu của lớp đó cũng trở thành một phiên dữ liệu dùng chung.

Cũng tránh khẳng định quá tuyệt đối rằng mọi tối ưu khởi động của JDK chỉ có metadata và không bao giờ có đối tượng heap. Các cơ chế cache khởi động hiện hành có thể lưu những dữ liệu/đối tượng được lựa chọn theo hợp đồng cụ thể. Ví dụ tài liệu JDK hiện hành mô tả AOT cache chứa lớp Java và heap object.

Điểm cần giữ là **lưu/tái sử dụng artifact khởi động không tạo quan hệ cập nhật trạng thái mutable giữa hai JVM đang chạy**. Không dùng cơ chế này thay thế thiết kế sở hữu dữ liệu của ứng dụng. [Java: Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#ahead-of-time-cache)

## 8. Hệ quả khi đánh giá hiệu năng và bộ nhớ

### Giảm metadata lặp lại không đồng nghĩa giảm mọi phần của heap

Giả sử nhiều tiến trình dùng cùng bộ thư viện, mỗi tiến trình lại giữ một lượng lớn dữ liệu nghiệp vụ. Chia sẻ dữ liệu lớp có thể giúp phần dữ liệu lớp lặp lại, nhưng không tự làm biến mất các danh sách, map hoặc đối tượng nghiệp vụ riêng.

Khi heap tăng theo số người dùng hoặc số bản ghi cache, cần kiểm tra vòng đời và lượng dữ liệu ứng dụng giữ lại. Không mặc định bật CDS sẽ giải quyết được tăng trưởng đó.

### Tổng bộ nhớ hiển thị cần được đọc theo cách hạch toán của hệ điều hành

Một trang chỉ đọc được nhiều tiến trình ánh xạ có thể xuất hiện trong số đo của từng tiến trình. Cộng máy móc tất cả số bộ nhớ hiển thị có thể không phản ánh đúng phần vật lý dùng chung.

Vì vậy, khi so sánh, cần nêu rõ đang đo heap, bộ nhớ riêng hay một chỉ số footprint của hệ điều hành. Tránh kết luận “không tiết kiệm” chỉ vì một chỉ số của một tiến trình không giảm theo trực giác. Tài liệu CDS cũng lưu ý việc ánh xạ trang có thể làm số liệu hiển thị trên Windows khó đọc theo phép cộng đơn giản.

### Kiểm chứng ngữ nghĩa tách khỏi đo hiệu năng

Ví dụ giỏ hàng kiểm chứng ranh giới trạng thái; nó không phải benchmark startup hoặc phép đo mức tiết kiệm bộ nhớ.

Nếu mục tiêu là đánh giá CDS cho ứng dụng thật, phải dùng cùng artifact/cấu hình và phép đo phù hợp, đồng thời xác nhận archive thực sự được dùng. Một lần chạy nhỏ với stdout giống nhau không cho phép tuyên bố phần trăm cải thiện.

## 9. Những câu dễ nói sai

| Câu nói | Cách diễn đạt chính xác hơn |
|---|---|
| “Hai JVM dùng cùng lớp nên có chung biến static” | Có thể tái sử dụng dữ liệu lớp; static mutable vẫn theo lớp/phiên JVM tương ứng |
| “Cùng Class nghĩa là cùng object” | Nhiều instance có thể cùng Class nhưng giữ field riêng |
| “final List là bất biến” | Tham chiếu final không cho gán lại; nội dung List vẫn có thể đổi |
| “CDS đã bật nên mọi class đều từ archive” | Cần xem phạm vi archive và bằng chứng nguồn nạp của từng lớp |
| “Lớp ứng dụng nằm trong AppCDS nên session cũng được lưu chung” | Archive lớp không tự lưu/đồng bộ session nghiệp vụ |
| “Thêm một JVM không cần thêm heap vì lớp đã chia sẻ” | Mỗi JVM vẫn cần tài nguyên cho trạng thái riêng của nó |
| “Static cache là cache toàn cụm” | Static chỉ không đủ để thiết lập giao tiếp và nhất quán giữa các instance |
| “Bật CDS sửa được race condition” | Race condition thuộc cách truy cập trạng thái dùng chung trong chương trình |

## 10. Thực hành xác định chủ sở hữu dữ liệu

Với một field hoặc đối tượng cụ thể, hãy tự trả lời lần lượt:

1. Nó là thông tin mô tả mã/lớp hay giá trị ứng dụng đang thay đổi?
2. Giá trị được tạo bởi lần new nào, hay được giữ trong field static của lớp nào?
3. Những đối tượng/luồng nào thật sự cùng giữ tham chiếu tới nó?
4. Ranh giới JVM có bị vượt qua không; nếu có, cơ chế truyền dữ liệu nằm ở đâu?
5. Bằng chứng đang dùng là log nguồn lớp, kết quả chương trình hay số đo bộ nhớ?

Bài tập với chương trình mẫu:

- Thêm một món vào second và kiểm tra hai size tăng độc lập.
- Tạo biến third trỏ cùng first; thêm qua third và giải thích vì sao first thấy thay đổi. Đây là dùng chung đối tượng qua tham chiếu.
- Chạy chương trình hai lần và giải thích vì sao bộ đếm static không tự tích lũy qua hai JVM.
- Đọc log nguồn lớp, đánh dấu chính xác lớp nào được xác nhận từ archive; không dùng dấu hiệu đó để suy ra số đối tượng nghiệp vụ.

Phân biệt được **phần dữ liệu phục vụ lớp** và **giá trị ứng dụng sở hữu khi chạy** giúp hiểu đúng lợi ích của CDS, thiết kế trạng thái và diễn giải số đo hiệu năng mà không gán cho tính năng chia sẻ những khả năng nó không cung cấp.
