# Phân biệt iterator fail-fast, ảnh chụp và nhất quán yếu

Một iterator được tạo khi collection đang ở trạng thái `S0`. Trước khi iterator duyệt hết, chương trình thêm, xóa hoặc thay dữ liệu để collection chuyển sang `S1`. Iterator sẽ làm gì?

Có ba hợp đồng cần phân biệt:

- **Fail-fast:** cố phát hiện sửa đổi không được phép để báo lỗi sử dụng.
- **Ảnh chụp (snapshot):** tiếp tục duyệt trạng thái mà iterator đã chụp.
- **Nhất quán yếu (weakly consistent):** cho phép duyệt cùng với cập nhật theo bảo đảm của nguồn, nhưng không cung cấp một ảnh chụp toàn bộ tại một thời điểm.

Chúng khác nhau về ý nghĩa dữ liệu nhìn thấy, cách xử lý thay đổi và chi phí. Không thể chọn chỉ bằng câu hỏi “có ném ngoại lệ hay không”.

Bài lấy Java 17 làm mốc. Bốn chương trình hoàn chỉnh đã được biên dịch với `--release 17` và chạy. Với ví dụ nhất quán yếu, stdout của một lần chạy được trình bày riêng với những bảo đảm có thể dựa vào; không biến một kết quả quan sát thành lời hứa của mọi lần thực thi.

Sau bài học, bạn có thể:

- Nhận diện ba kiểu duyệt qua hợp đồng của nguồn thực tế.
- Giải thích vì sao `ConcurrentModificationException` không đồng nghĩa luôn có nhiều luồng.
- Phân biệt snapshot cấu trúc với bản sao sâu của phần tử.
- Giải thích vì sao collection an toàn luồng chưa tạo ra lượt duyệt nguyên tử.
- Chọn giữa khóa, sao chép và cấu trúc đồng thời theo yêu cầu dữ liệu.

## 1. Bắt đầu từ một thay đổi trong vòng đời iterator

Giả sử nguồn ban đầu là:

```text
[A, B, C]
```

Trình tự:

```text
t0: tạo iterator
t1: iterator nhận A
t2: nguồn bị thêm D hoặc xóa B
t3: iterator tiếp tục
```

Câu hỏi không chỉ là “vòng lặp còn chạy được không”. Ta còn cần biết:

1. Dữ liệu mà iterator tiếp tục nhận thuộc trạng thái nào?
2. Thay đổi ở `t2` có được hợp đồng của nguồn cho phép không?
3. Có thể dùng kết quả để kết luận về toàn nguồn tại một thời điểm không?
4. Ai bảo vệ các đối tượng phần tử nếu chúng cũng thay đổi?

Cùng một cú pháp enhanced for có thể đi qua iterator với những hợp đồng rất khác. Cú pháp vòng lặp không tự quyết định cách nhất quán.

## 2. Bảng đối chiếu

| Câu hỏi | Fail-fast | Snapshot | Nhất quán yếu |
| --- | --- | --- | --- |
| Mục tiêu chính | Phát hiện sửa đổi không hợp lệ | Duyệt một trạng thái cấu trúc đã xác định | Tiếp tục duyệt trong bối cảnh nguồn được cập nhật |
| Có phải ảnh chụp toàn nguồn? | Không | Có đối với phạm vi snapshot được cam kết | Không mặc định |
| Thay đổi sau khi tạo iterator | Có thể bị phát hiện là lỗi | Không đổi tập tham chiếu đã chụp | Có thể được phản ánh theo hợp đồng nguồn |
| CME do thay đổi nguồn | Cơ chế phát hiện ở mức cố gắng | Không xảy ra với thay đổi được hợp đồng snapshot cho phép | Không xảy ra đối với cập nhật mà hợp đồng duyệt cho phép |
| Chỉnh sửa qua iterator | Tùy nguồn và thao tác | Iterator của CopyOnWriteArrayList không hỗ trợ | Tùy loại cụ thể |
| Ví dụ trong bài | ArrayList | CopyOnWriteArrayList | Các góc nhìn của ConcurrentHashMap |

Bảng là cách định hướng. Khi viết mã, vẫn phải xác định đúng lớp và đúng API tạo iterator. Không suy từ tên giao diện `List`, `Set` hoặc `Map` ra toàn bộ chính sách duyệt.

“Không có CME” cũng không trả lời được câu hỏi snapshot: cả snapshot và nhất quán yếu đều có thể tiếp tục khi nguồn thay đổi, nhưng kết quả dữ liệu mang ý nghĩa khác nhau.

## 3. Fail-fast: công cụ phát hiện lỗi sử dụng

Iterator của `ArrayList` phát hiện những sửa đổi cấu trúc không đi qua cơ chế được iterator cho phép. Thêm hoặc xóa là những ví dụ điển hình; thay giá trị một phần tử bằng `set` không được ArrayList xem là sửa đổi cấu trúc. Cơ chế này không có bảo đảm phát hiện mọi vi phạm, đặc biệt khi cập nhật không được đồng bộ. Xem [hợp đồng ArrayList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### Mô hình giải thích bằng số phiên bản

Có thể hình dung một lớp triển khai theo dõi:

```text
Phiên bản cấu trúc của nguồn
Phiên bản mà iterator đang kỳ vọng
```

Khi phát hiện hai thông tin không còn phù hợp, iterator báo rằng nó không thể tiếp tục theo cách sử dụng hiện tại.

Đây là mô hình để hiểu ý định phát hiện lỗi, không phải yêu cầu mọi iterator phải có cùng tên trường, thời điểm kiểm tra hoặc cách cài đặt.

Nó giúp giải thích hai tình huống:

- Sửa qua chính iterator đang dùng, nếu được hỗ trợ, có thể cập nhật trạng thái duyệt một cách phối hợp.
- Sửa trực tiếp qua nguồn có thể làm iterator đang tồn tại không còn hợp lệ.

### Một luồng cũng có thể gây ConcurrentModificationException

Một luồng có thể tạo iterator, thêm trực tiếp vào danh sách rồi gọi iterator tiếp. Không cần có luồng thứ hai để vi phạm hợp đồng. Tài liệu [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html) cũng nhấn mạnh đây là cơ chế tìm lỗi, không phải điều kiện để bảo đảm tính đúng đắn.

Vì vậy, không nên:

- Xem có ngoại lệ là bằng chứng chắc chắn đã có hai luồng chạy cùng lúc.
- Xem không có ngoại lệ là bằng chứng chương trình không có lỗi.
- Bắt ngoại lệ rồi tự tiếp tục trên iterator cũ.
- Dùng việc thử đến khi không còn ngoại lệ làm cơ chế đồng bộ.

Một thao tác có thể đã gây tác dụng phụ trước khi lỗi được phát hiện. Việc chạy lại toàn bộ vòng lặp còn có thể lặp lại công việc, nên “catch rồi retry” không phải cách sửa tổng quát.

## 4. Chương trình fail-fast trong một luồng

Tạo tệp **`FailFastIteratorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class FailFastIteratorDemo {
    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>(List.of(1, 2, 3));
        Iterator<Integer> cursor = values.iterator();

        System.out.println("first = " + cursor.next());
        values.add(4);

        try {
            cursor.next();
        } catch (ConcurrentModificationException exception) {
            System.out.println("external add = "
                    + exception.getClass().getSimpleName());
        }

        Iterator<Integer> supported = values.iterator();
        while (supported.hasNext()) {
            if (supported.next() % 2 == 0) {
                supported.remove();
            }
        }
        System.out.println("after iterator removal = " + values);

        List<String> labels = new ArrayList<>(List.of("A", "B"));
        Iterator<String> labelCursor = labels.iterator();
        labels.set(1, "B*");

        List<String> observed = new ArrayList<>();
        labelCursor.forEachRemaining(observed::add);
        System.out.println("replacement observed = " + observed);
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 FailFastIteratorDemo.java
java -Dfile.encoding=UTF-8 FailFastIteratorDemo
```

Stdout đã kiểm chứng:

```text
first = 1
external add = ConcurrentModificationException
after iterator removal = [1, 3]
replacement observed = [A, B*]
```

### Đọc ba phần thử nghiệm

**Phần thứ nhất:**

1. Iterator nhận `1`.
2. Chính luồng đó thêm `4` trực tiếp vào danh sách.
3. Lần `next` tiếp theo phát hiện sửa đổi và ném CME trong tình huống cụ thể này.

Đây là ví dụ tái hiện có kiểm soát của ArrayList, không phải khẳng định rằng mọi kiểu thay đổi trên mọi iterator sẽ báo lỗi tại cùng điểm.

**Phần thứ hai:**

- Chương trình tạo iterator mới trên danh sách hiện tại.
- Nó xóa số chẵn bằng `supported.remove()`, qua chính iterator đang duyệt.
- Kết quả là `[1, 3]`.

Việc tạo iterator mới ở đây bắt đầu một lượt xử lý đã được thiết kế lại sau thử nghiệm. Nó không minh họa một thuật toán tự phục hồi bằng cách lặp vô hạn sau mỗi lỗi.

**Phần thứ ba:**

- Iterator được tạo trước khi `labels.set(1, "B*")`.
- Lượt duyệt vẫn đọc `[A, B*]` trong thử nghiệm.
- Ví dụ cho thấy fail-fast không có nghĩa “đóng băng tất cả dữ liệu kể từ thời điểm tạo”.

### Không biến đặc tính của ArrayList thành quy tắc cho mọi collection

Khái niệm sửa đổi cấu trúc phụ thuộc loại nguồn. Đặc biệt:

- Thay giá trị không phải thêm/xóa phần tử.
- Sửa nội dung một đối tượng phần tử còn là một lớp thay đổi khác.
- Những thao tác như sắp xếp hoặc thay đổi qua góc nhìn cần được xem theo hợp đồng cụ thể.

Không nên đoán rằng chỉ cần giữ nguyên `size` thì mọi thay đổi đều được iterator chấp nhận.

## 5. Snapshot: giữ trạng thái cấu trúc của một thời điểm

Iterator của `CopyOnWriteArrayList` giữ tham chiếu tới trạng thái mảng tại lúc nó được tạo. Các lần thêm, xóa hoặc thay phần tử của danh sách về sau không đổi dữ liệu cấu trúc mà iterator đó duyệt. Các thao tác thay đổi qua iterator như remove, set, add không được hỗ trợ. Xem [CopyOnWriteArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

Có thể vẽ mô hình:

```text
t0:
iterator cũ -> mảng chứa A, B, C
danh sách   -> mảng chứa A, B, C

t1 sau thay đổi:
iterator cũ -> mảng cũ chứa A, B, C
danh sách   -> trạng thái mới chứa A*, C, D
```

Các phần tử mới thuộc danh sách hiện tại không tự xuất hiện trong iterator cũ.

### Snapshot không có nghĩa danh sách sống ngừng thay đổi

Hai sự thật có thể đồng thời đúng:

- Một bên tiếp tục cập nhật danh sách.
- Một iterator đang tồn tại vẫn duyệt một tập tham chiếu ổn định.

Điều này phù hợp với những bài toán mà một lượt xử lý được phép dùng danh sách tại lúc bắt đầu, chẳng hạn danh sách bộ lắng nghe sự kiện cho một lần thông báo. Một bộ lắng nghe mới được đăng ký có thể chỉ cần tham gia lượt sau, theo chính sách ứng dụng đã chọn.

### Snapshot cấu trúc không tự là bản sao sâu

Nếu phần tử là một đối tượng khả biến, snapshot vẫn có thể giữ tham chiếu tới chính đối tượng đó.

Do đó cần phân biệt:

1. Thay phần tử ở một vị trí của danh sách.
2. Sửa thuộc tính bên trong đối tượng mà vị trí đó đang tham chiếu.

Chương trình sau kiểm chứng sự khác biệt trong một luồng, để loại khỏi ví dụ những câu hỏi riêng về khả năng nhìn thấy dữ liệu giữa các luồng.

## 6. Chương trình snapshot và phần tử khả biến

Tạo tệp **`SnapshotIteratorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class SnapshotIteratorDemo {
    private static final class Score {
        private int value;

        private Score(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        CopyOnWriteArrayList<String> values =
                new CopyOnWriteArrayList<>(List.of("A", "B", "C"));
        Iterator<String> beforeChanges = values.iterator();

        values.set(0, "A*");
        values.remove("B");
        values.add("D");

        List<String> oldView = new ArrayList<>();
        beforeChanges.forEachRemaining(oldView::add);

        System.out.println("old iterator = " + oldView);
        System.out.println("current list = " + values);

        Iterator<String> readOnlyCursor = values.iterator();
        readOnlyCursor.next();
        try {
            readOnlyCursor.remove();
        } catch (UnsupportedOperationException exception) {
            System.out.println("iterator remove = "
                    + exception.getClass().getSimpleName());
        }

        Score sharedScore = new Score(10);
        CopyOnWriteArrayList<Score> scores =
                new CopyOnWriteArrayList<>(List.of(sharedScore));
        Iterator<Score> oldScores = scores.iterator();

        sharedScore.value = 99;
        scores.set(0, new Score(20));

        System.out.println("old element state = " + oldScores.next().value);
        System.out.println("current element state = " + scores.get(0).value);
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 SnapshotIteratorDemo.java
java -Dfile.encoding=UTF-8 SnapshotIteratorDemo
```

Stdout đã kiểm chứng:

```text
old iterator = [A, B, C]
current list = [A*, C, D]
iterator remove = UnsupportedOperationException
old element state = 99
current element state = 20
```

### Nhóm chuỗi

- Iterator được tạo khi danh sách là `[A, B, C]`.
- Danh sách sống đổi thành `[A*, C, D]`.
- Iterator cũ vẫn duyệt `[A, B, C]`.
- Gọi remove qua iterator mới vẫn bị từ chối: khả năng sửa danh sách không kéo theo khả năng sửa qua iterator.

### Nhóm Score

1. Iterator cũ giữ tham chiếu tới đối tượng Score ban đầu.
2. Thuộc tính của đối tượng đó được đổi từ `10` thành `99`.
3. Danh sách sống được thay phần tử bằng đối tượng Score mới mang giá trị `20`.
4. Iterator cũ nhận đối tượng ban đầu, nên thấy `99`; danh sách hiện tại có đối tượng khác mang `20`.

Đây là bằng chứng rằng ảnh chụp các tham chiếu không tự sao chép trạng thái sâu của phần tử.

Nếu nhiều luồng cùng sửa thuộc tính Score, ứng dụng còn cần chính sách bất biến hoặc đồng bộ cho chính Score. Dùng collection đồng thời không tự biến mọi trường dữ liệu bên trong thành an toàn luồng.

### Chi phí cần cân nhắc

Từ mô hình giữ mảng cũ, có thể suy ra một iterator tồn tại lâu có thể kéo dài thời gian những tham chiếu cũ còn được giữ lại. Việc ghi trong mô hình copy-on-write cũng có chi phí sao chép cấu trúc.

Do đó, hãy cân nhắc tỷ lệ đọc/ghi, số phần tử và thời gian giữ iterator. Đừng chọn copy-on-write chỉ vì muốn bỏ một ngoại lệ trong mã đang sử dụng sai nguồn.

## 7. Nhất quán yếu: duyệt được trong khi nguồn cập nhật

Các cấu trúc đồng thời có thể cung cấp iterator cho phép duyệt cùng những thao tác cập nhật được hỗ trợ. Gói [java.util.concurrent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html) gọi đây là duyệt nhất quán yếu: dữ liệu sau khi tạo iterator có thể được phản ánh, nhưng không phải mọi thay đổi đều được bảo đảm xuất hiện.

Với `ConcurrentHashMap`, iterator không ném CME vì các cập nhật được hỗ trợ; những phần tử trả về phản ánh các trạng thái tại hoặc sau lúc tạo iterator. Nó không cung cấp một lần chụp nguyên tử toàn map. Các iterator của lớp này được thiết kế để một luồng sử dụng tại một thời điểm. Xem [hợp đồng ConcurrentHashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

### Những kết luận không được tự thêm

Không nên suy ra rằng iterator nhất quán yếu:

- Luôn nhìn thấy toàn bộ dữ liệu mới nhất khi vòng lặp kết thúc.
- Luôn bỏ qua mọi dữ liệu bị xóa.
- Luôn giữ nguyên dữ liệu tại lúc bắt đầu.
- Tự chụp toàn bộ map tại một thời điểm duy nhất.
- Tự bảo đảm bất biến nghiệp vụ liên quan nhiều khóa.

“Yếu” không có nghĩa dữ liệu tùy tiện hoặc không có hợp đồng. Nó có nghĩa mức quan sát được cam kết khác với snapshot nguyên tử; phải dựa vào bảo đảm của đúng lớp.

### Nhất quán và thứ tự là hai câu hỏi riêng

Một map có thể không hứa thứ tự duyệt theo tên khóa, trong khi vẫn bảo đảm việc duyệt phù hợp với các cập nhật được hỗ trợ.

Nếu cần trình bày kết quả theo thứ tự, có thể sắp xếp **những gì đã quan sát được**. Tuy nhiên, bước sắp xếp đó không quay ngược thời gian để làm cho dữ liệu đã thu thập trở thành một snapshot nguyên tử.

## 8. Chương trình quan sát dữ liệu cũ và mới trong cùng lượt duyệt

Tạo tệp **`WeakIteratorDemo.java`**:

```java
import java.util.Iterator;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;

public class WeakIteratorDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> values = new ConcurrentHashMap<>();
        values.put("A", 10);
        values.put("B", 20);
        values.put("C", 30);

        Iterator<Map.Entry<String, Integer>> cursor =
                values.entrySet().iterator();
        Map<String, Integer> observed = new TreeMap<>();

        Map.Entry<String, Integer> first = cursor.next();
        observed.put(first.getKey(), first.getValue());

        Thread writer = new Thread(() -> {
            values.replaceAll((key, value) -> value + 100);
            values.put("D", 40);
        });

        writer.start();
        writer.join();

        while (cursor.hasNext()) {
            Map.Entry<String, Integer> entry = cursor.next();
            observed.put(entry.getKey(), entry.getValue());
        }

        System.out.println("observed in this run = " + observed);
        System.out.println("after writer = " + new TreeMap<>(values));
        System.out.println("traversal completed = true");
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 WeakIteratorDemo.java
java -Dfile.encoding=UTF-8 WeakIteratorDemo
```

Stdout của **lần chạy đã kiểm chứng**:

```text
observed in this run = {A=10, B=120, C=130, D=40}
after writer = {A=110, B=120, C=130, D=40}
traversal completed = true
```

Dòng `observed in this run` là dữ liệu quan sát trong lần chạy này, không phải giá trị cố định để khẳng định cho mọi triển khai hoặc mọi cách thực thi. Map không có thứ tự duyệt bắt buộc theo bảng chữ cái; TreeMap trong mã chỉ sắp xếp đầu ra sau khi thu thập.

### Trình tự được chương trình kiểm soát

1. Luồng chính tạo iterator và nhận một entry đầu tiên.
2. Nó giữ lại khóa và giá trị entry đó trong bản ghi quan sát.
3. Luồng ghi cập nhật các giá trị cũ rồi thêm khóa D.
4. `join()` chờ luồng ghi hoàn tất.
5. Luồng chính dùng **iterator đã tạo từ trước** để duyệt tiếp.

Không dùng một khoảng ngủ để đoán rằng luồng ghi “chắc đã xong”. `join` xác định rõ thời điểm hoàn tất và tạo quan hệ nhìn thấy cần thiết giữa hai luồng trong ví dụ.

### Ý nghĩa của kết quả đã quan sát

Trong lần chạy này:

- Giá trị A được thu trước cập nhật, nên bản ghi quan sát giữ A bằng `10`.
- Các giá trị B và C quan sát sau đó là giá trị đã tăng.
- D mới thêm cũng xuất hiện.
- Map sau khi luồng ghi kết thúc có A bằng `110`.

Vì D chỉ được thêm sau khi đã tăng tất cả các giá trị cũ, không có thời điểm nào nguồn vừa có A bằng `10` vừa có D bằng `40`. Vậy tổ hợp đã quan sát không phải ảnh chụp toàn map tại một thời điểm.

Đây là lập luận về **kết quả thực tế của lần chạy đã trình bày**. Nếu một lần chạy khác không nhìn thấy D hoặc có quan sát khác được hợp đồng cho phép, không thể kết luận iterator bị lỗi chỉ vì khác ví dụ.

### Những gì không đổi trong ví dụ

Sau khi `writer.join()` hoàn tất và không còn bên ghi nào:

- Mọi giá trị A, B, C đã được tăng trong map sống.
- Khóa D đã được thêm.
- Việc in map sống bằng TreeMap lúc đó phản ánh trạng thái cuối đang ổn định.

Sự kiểm tra trạng thái cuối này khác với đòi hỏi iterator cũ phải nhìn thấy một trạng thái cuối hoàn chỉnh.

## 9. Ba loại iterator không phải ba mức “an toàn” tăng dần

Không có cách xếp chung rằng fail-fast kém, snapshot khá, nhất quán yếu tốt nhất.

### Khi chương trình chỉ có một bên sở hữu dữ liệu

Nếu một phương thức quản lý riêng danh sách của nó, một ArrayList thông thường và việc sửa đúng qua iterator có thể là đủ. Đổi sang cấu trúc đồng thời không tự làm thuật toán đơn giản hơn.

### Khi một lượt xử lý cần danh sách tại lúc bắt đầu

Một snapshot phù hợp nếu các cập nhật được chấp nhận cho lượt sau. Cần xét cả phần tử khả biến và chi phí giữ các phiên bản cấu trúc.

### Khi cần đọc trong lúc nhiều bên cập nhật

Duyệt nhất quán yếu có thể phù hợp cho những quan sát chấp nhận dữ liệu trong một khoảng thời gian, ví dụ hiển thị trạng thái hoạt động với yêu cầu được định nghĩa tương ứng.

Nếu muốn một báo cáo chính xác của toàn bộ dữ liệu tại cùng thời điểm, không nên tự coi lượt duyệt đó đáp ứng yêu cầu.

### Khi cần thay đổi nghiệp vụ gồm nhiều bước

Việc “tìm thấy một phần tử rồi cập nhật” hoặc “kiểm tra rồi thêm” cần chính sách phối hợp riêng.

Hợp đồng iterator trả lời cách duyệt khi nguồn thay đổi. Nó không tự biến một chuỗi thao tác của ứng dụng thành giao dịch nguyên tử.

## 10. Khóa cả lượt duyệt hoặc tạo bản sao được bảo vệ

Một lựa chọn khác là ngăn các cập nhật được phối hợp trong lúc duyệt hoặc trong lúc tạo bản sao.

Với danh sách bọc bằng `Collections.synchronizedList`, tài liệu yêu cầu người dùng đồng bộ thủ công trên chính danh sách bọc khi duyệt. Các lời gọi được đồng bộ riêng lẻ không mặc định giữ khóa suốt cả vòng lặp. Xem [Collections.synchronizedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

Có hai chiến lược:

| Chiến lược | Đánh đổi |
| --- | --- |
| Giữ khóa trong suốt lượt duyệt | Nguồn được giữ ổn định theo giao thức khóa; bên ghi có thể phải chờ |
| Giữ khóa để sao chép, rồi xử lý bản sao ngoài khóa | Thêm chi phí sao chép; giảm thời gian khóa cho phần xử lý dài |

Điều kiện là các bên ghi phải tuân theo cùng giao thức. Một khóa mà bên ghi không sử dụng không tự chặn chúng.

### Chương trình hoàn chỉnh

Tạo tệp **`LockedSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class LockedSnapshotDemo {
    public static void main(String[] args) {
        List<String> shared = Collections.synchronizedList(
                new ArrayList<>(List.of("A", "B", "C")));

        List<String> snapshot;
        synchronized (shared) {
            snapshot = new ArrayList<>(shared);
        }

        shared.add("D");

        System.out.println("snapshot = " + snapshot);
        System.out.println("live list = " + shared);

        synchronized (shared) {
            for (String value : shared) {
                System.out.println("locked visit = " + value);
            }
        }
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 LockedSnapshotDemo.java
java -Dfile.encoding=UTF-8 LockedSnapshotDemo
```

Stdout đã kiểm chứng:

```text
snapshot = [A, B, C]
live list = [A, B, C, D]
locked visit = A
locked visit = B
locked visit = C
locked visit = D
```

### Đọc hai cách sử dụng

- Bản sao được tạo trong khối khóa.
- Sau khi thêm D vào nguồn, bản sao vẫn chỉ có A, B, C.
- Vòng lặp cuối giữ khóa trên danh sách bọc để minh họa vùng đồng bộ bao trùm cả lượt duyệt.

Ví dụ dùng một luồng để trình bày rõ ranh giới thao tác và đầu ra. Khi áp dụng nhiều luồng, các bên phải dùng danh sách bọc hoặc cùng cơ chế bảo vệ; không giữ một tham chiếu khác tới mảng/danh sách nền rồi sửa qua đường bỏ qua khóa.

Đây vẫn là sao chép nông của phần tử. Nếu phần tử có dữ liệu khả biến cần ảnh chụp sâu, ứng dụng phải thiết kế cách chụp trạng thái phần tử phù hợp.

### Không mặc định new ArrayList(concurrentValues) là snapshot nguyên tử

Một bản sao được tạo bằng cách thu thập từ nguồn nhất quán yếu có thể giữ cố định **kết quả thu thập**, nhưng kết quả đó vẫn có thể được lấy từ nhiều thời điểm.

Tương tự, chỉ viết `synchronized(map)` quanh bên đọc không làm những lời gọi cập nhật ConcurrentHashMap ở nơi khác tự sử dụng khóa đó. Muốn một ảnh chụp phối hợp, cần giao thức mà tất cả các bên liên quan cùng tuân thủ, hoặc một thiết kế công bố trạng thái bất biến theo phiên bản.

## 11. Các ngộ nhận cần loại bỏ

### “Fail-safe” là một hợp đồng đầy đủ

Đôi khi tên này được dùng để gộp những iterator không ném CME. Nó không trả lời được iterator dùng snapshot hay nhất quán yếu, có hỗ trợ xóa không, hoặc bảo đảm dữ liệu gì.

Khi phân tích, hãy nói đúng hợp đồng cụ thể và tên lớp thay vì dừng ở một nhãn chung.

### Không có CME nghĩa là thread-safe

Không có ngoại lệ không chứng minh truy cập đang hợp lệ. Có thể bạn đang dùng snapshot, một cấu trúc đồng thời, hoặc đơn giản chưa gặp đường phát hiện lỗi.

Ngoài ra, collection an toàn luồng không có nghĩa một đối tượng iterator nên được nhiều luồng dùng chung tùy ý.

### Snapshot nghĩa là mọi dữ liệu bên trong bị đóng băng

Ví dụ Score cho thấy tham chiếu cũ vẫn dẫn tới một đối tượng khả biến. Bất biến cấu trúc và bất biến phần tử cần được đánh giá riêng.

### Nhất quán yếu luôn nhìn thấy bản mới nhất

Một lượt duyệt không mặc định là một thao tác đọc nguyên tử của toàn nguồn. Nếu yêu cầu nghiệp vụ dùng chữ “mới nhất”, cần định nghĩa mới nhất ở thời điểm nào và mức phối hợp cần thiết.

### Chuyển vòng for-each thành vòng chỉ số là hết lỗi

Thay cú pháp không tự tạo chính sách đồng bộ. Thêm/xóa còn làm thay đổi chỉ số và có thể gây bỏ sót hoặc truy cập sai.

### Bắt CME rồi bỏ qua là đã xử lý

Bỏ qua lỗi có thể để một phần dữ liệu chưa được xử lý hoặc làm mất khả năng nhận biết tác dụng phụ đã xảy ra. Cần sửa cách sở hữu, phối hợp hoặc duyệt dữ liệu theo hợp đồng.

### Chỉ cần kiểm tra size trước và sau

Hai thời điểm có cùng kích thước vẫn có thể chứa các phần tử hoặc giá trị khác nhau. Một số thay đổi còn có thể thêm rồi xóa, khiến số lượng trở lại như cũ.

Size không phải số phiên bản nghiệp vụ hay bằng chứng toàn bộ lượt duyệt đã nhất quán.

## 12. Cách kiểm chứng mà không phụ thuộc vào may rủi lịch chạy

Khi viết thử nghiệm:

1. Xác định rõ thời điểm tạo iterator.
2. Ghi lại thay đổi nào được làm trước khi lấy phần tử tiếp theo.
3. Dùng `join`, latch hoặc cơ chế phối hợp phù hợp nếu cần một thứ tự sự kiện.
4. Phân biệt giá trị được hợp đồng bảo đảm với một kết quả quan sát.
5. Không dùng ngủ một khoảng thời gian làm bằng chứng đồng bộ.
6. Không khẳng định hợp đồng tổng quát từ một lần không có ngoại lệ.

Ví dụ trong bài cố định trình tự sự kiện để làm rõ **vòng đời iterator**, nhưng vẫn không ép iterator nhất quán yếu thành snapshot.

Một số tiêu chí kiểm tra:

| Loại thử nghiệm | Điều nên xác minh |
| --- | --- |
| Fail-fast cụ thể | Tái hiện vi phạm ở nguồn và chuỗi thao tác đã xác định |
| Snapshot | Iterator cũ giữ tập tham chiếu đã chụp sau các cập nhật nguồn |
| Phần tử khả biến | Phân biệt thay phần tử với sửa đối tượng chung |
| Nhất quán yếu | Chỉ đòi các bảo đảm của lớp; không ép một tập kết quả tùy ý thành cố định |
| Khóa hoặc bản sao | Kiểm tra mọi bên ghi đi qua cùng giao thức bảo vệ |

Với hệ thống thực, cần thêm kiểm tra rằng các tác vụ không làm lặp hoặc bỏ công việc ngoài chính sách, và rằng dữ liệu phần tử cũng được công bố, đọc, sửa một cách hợp lệ.

## 13. Thực hành

### Bài 1: phân loại yêu cầu

Với mỗi tình huống, giải thích hợp đồng phù hợp:

- Một phương thức lọc danh sách do chính nó sở hữu.
- Một lượt gửi sự kiện dùng danh sách bộ lắng nghe tại lúc bắt đầu.
- Một màn hình trạng thái chấp nhận quan sát các cập nhật trong thời gian duyệt.
- Một báo cáo cần trạng thái toàn bộ dữ liệu tại một thời điểm được xác định.

Nêu lý do chọn, không chỉ tên collection.

### Bài 2: thử thay cấu trúc và thay phần tử

Từ `FailFastIteratorDemo`, tạo các tình huống tách biệt:

1. Thêm phần tử sau khi tạo iterator.
2. Thay một phần tử bằng set.
3. Xóa qua chính iterator khi được hỗ trợ.

Giải thích các kết quả theo hợp đồng ArrayList và không suy rộng thời điểm ném lỗi sang mọi lớp.

### Bài 3: phân biệt hai lớp snapshot

Từ `SnapshotIteratorDemo`:

- Thay đối tượng ở một vị trí sau khi tạo iterator.
- Trong một thử nghiệm riêng, chỉ sửa thuộc tính của đối tượng mà iterator đang giữ.
- Vẽ các tham chiếu cũ và mới.
- Giải thích trường hợp nào đổi cấu trúc quan sát và trường hợp nào đổi trạng thái đối tượng chung.

### Bài 4: kiểm tra phát biểu về nhất quán yếu

Đánh giá các phát biểu:

1. “Không có CME nên dữ liệu là snapshot.”
2. “Dùng TreeMap để in kết quả nên lượt đọc đã nguyên tử.”
3. “Sau join, map sống đã hoàn tất cập nhật nên iterator cũ bắt buộc thấy toàn bộ trạng thái đó.”
4. “Một kết quả quan sát không trùng trạng thái cuối chưa đủ để kết luận ConcurrentHashMap bị lỗi.”
5. “Collection đồng thời thì các bước kiểm tra rồi cập nhật của ứng dụng tự trở thành một thao tác nguyên tử.”

Hãy liên hệ từng phát biểu với trình tự trong `WeakIteratorDemo`.

### Bài 5: thiết kế một bản sao có ý nghĩa

Giả sử có một danh sách dùng chung và mỗi phần tử là đối tượng khả biến.

Hãy mô tả:

- Thời điểm muốn lấy dữ liệu.
- Bên nào phải bị chặn hoặc phối hợp trong lúc chụp.
- Chỉ cần sao chép tham chiếu hay phải chụp cả thuộc tính phần tử.
- Bản sao sẽ được xử lý ngoài khóa như thế nào.
- Giới hạn nào cần ghi rõ cho bên sử dụng.

Tiêu chí hoàn thành là phân biệt được hợp đồng iterator, tính nguyên tử của lượt đọc và tính an toàn của đối tượng phần tử, rồi chọn cơ chế đáp ứng đúng mức nhất quán cần có.
