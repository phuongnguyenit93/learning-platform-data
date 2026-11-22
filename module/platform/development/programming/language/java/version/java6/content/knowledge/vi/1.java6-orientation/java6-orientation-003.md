# Phân biệt hợp đồng API với chi tiết triển khai của từng JDK

## 1. Chương trình dựa vào điều được bảo đảm hay điều tình cờ quan sát được?

Khi học một API Java, ta có thể tìm thấy ba loại thông tin:

1. Tài liệu nói thao tác **phải có hành vi gì**.
2. Mã nguồn JDK cho thấy một bản triển khai **đang làm bằng cách nào**.
3. Một lần chạy cho thấy **trên môi trường này đã xảy ra điều gì**.

Ba loại thông tin đều có ích, nhưng không có cùng phạm vi bảo đảm.

Ví dụ, một danh sách được tài liệu hứa giữ thứ tự phần tử là một hợp đồng ta có thể dùng để viết chương trình. Tên lớp private mà một factory chọn để tạo danh sách thường không phải hợp đồng mà ứng dụng được phép phụ thuộc.

Câu hỏi thực dụng khi đọc tài liệu hoặc source là:

> Nếu đổi bản cập nhật JDK, nhà cung cấp hoặc cấu hình runtime, điều nào chương trình vẫn có quyền yêu cầu phải đúng?

Bài này dùng ví dụ trên Java hiện đại để minh họa nguyên tắc vẫn áp dụng hiện nay. Tên module Java 6 không có nghĩa phải chạy runtime cũ hay dựa vào tài liệu lịch sử khi hợp đồng hiện tại đã khác.

## 2. Hợp đồng API bao gồm những gì?

Hợp đồng API không chỉ là tên phương thức và kiểu trả về. Nó có thể quy định:

- Điều kiện đầu vào và trách nhiệm của nơi gọi.
- Kết quả, thứ tự và tác động lên đối tượng.
- Ngoại lệ khi vi phạm điều kiện.
- Khả năng sửa đổi hoặc quan hệ giữa view và dữ liệu gốc.
- Quy tắc null, identity, equality.
- Yêu cầu đồng thời và khả kiến bộ nhớ.
- Đặc tính hiệu năng khi tài liệu có nêu rõ.
- Hành vi của phương thức mặc định hoặc điểm mở rộng cho lớp con.

Hợp đồng cũng có thể cố ý để mở một phần: “không bảo đảm thứ tự”, “thao tác tùy chọn”, “best effort” hoặc “có thể dùng lại đối tượng”. Những chỗ để mở là một phần quan trọng của điều cần học.

Không được biến việc “chưa bị lỗi trong vài lần chạy” thành một điều kiện được bảo đảm mà tài liệu chưa hứa.

## 3. Chi tiết triển khai thường là những thông tin nào?

| Thông tin | Cách phân loại |
| --- | --- |
| Kết quả và ngoại lệ được tài liệu quy định | Hợp đồng API |
| Một thuật toán bắt buộc ổn định theo tài liệu | Thuộc tính được bảo đảm |
| Mảng nội bộ tăng theo đúng một tỉ lệ cụ thể | Chi tiết triển khai nếu không được API quy định |
| Tên lớp private được một factory trả về | Thường là chi tiết nội bộ |
| Kích thước đối tượng trong một cấu hình JVM | Kết quả phụ thuộc triển khai/cấu hình |
| Tác vụ được thread nào thực hiện khi API không hứa | Không được tự suy thành hợp đồng |
| Thứ tự HashMap tình cờ in ra trên một bộ dữ liệu | Quan sát, không phải thứ tự được bảo đảm |
| Thời gian một phép gọi trong một lần benchmark | Số đo của môi trường và phương pháp đó |

Một điểm dễ sai: **hiệu năng không phải lúc nào cũng chỉ là chi tiết triển khai**. Nếu Javadoc quy định độ phức tạp, đó là thông tin công khai cần xét. Phần để mở có thể là hệ số, cách cấp phát hoặc thuật toán cụ thể, không phải toàn bộ đặc tính.

Tương tự, một tài liệu dành cho một provider cụ thể có thể cam kết hành vi bổ sung của provider ấy. Đó là hợp đồng có phạm vi hẹp hơn, không tự trở thành bảo đảm cho mọi JDK/provider.

## 4. Ví dụ ArrayList: biết đặc tính, không đóng đinh chính sách tăng mảng

Tài liệu `ArrayList` mô tả các thao tác như `get()`, `set()` có thời gian hằng và `add()` có chi phí thời gian hằng khấu hao. Nó cũng nói chi tiết chính sách tăng capacity không được quy định vượt quá yêu cầu chi phí khấu hao đó. Xem [ArrayList](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html).

Vì vậy:

- Có thể dùng đặc tính công khai đó khi phân tích lựa chọn cấu trúc dữ liệu.
- Không coi mọi lần add đều có cùng độ trễ.
- Không viết logic ứng dụng dựa vào một công thức tăng mảng đọc được trong source của một bản JDK.
- Nếu muốn chuẩn bị dung lượng, dùng API công khai như constructor có capacity hoặc `ensureCapacity()`.

Quan sát một lần resize lớn không mâu thuẫn với thời gian hằng **khấu hao**. Khái niệm khấu hao nói về tổng chi phí trên một chuỗi thao tác, không hứa độ trễ giống nhau cho từng lần.

Một test kiểm tra đúng hệ số tăng mảng private có thể hỏng khi JDK thay đổi cách tối ưu dù hành vi công khai vẫn đúng. Test như vậy chỉ phù hợp nếu mục tiêu là kiểm chứng chính bản triển khai đó, không phải kiểm chứng nghiệp vụ của ứng dụng.

## 5. Ví dụ sắp xếp: ổn định có thể là hợp đồng, thuật toán có thể thay đổi

Với các thuật toán đa hình trong `Collections`, tài liệu phân biệt mô tả triển khai với điều kiện hành vi. Ví dụ, `sort` phải giữ tính ổn định, nhưng không bắt buộc mọi bản triển khai dùng cùng một thuật toán nội bộ. Xem [Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).

“Tính ổn định” ở đây nghĩa là những phần tử được comparator coi là bằng nhau giữ thứ tự tương đối ban đầu sau khi sắp xếp.

Ví dụ:

```text
Đầu vào:
first  : priority 1
second : priority 1
third  : priority 0

Sắp theo priority tăng dần:
third, first, second
```

Việc `first` vẫn đứng trước `second` dựa vào hợp đồng ổn định. Tên thuật toán, cách chia đoạn hay ngưỡng xử lý nội bộ không cần được ứng dụng biết để đạt mục tiêu đó.

Đừng mở rộng bảo đảm này sang mọi hàm sắp xếp, mọi kiểu dữ liệu hoặc một thuật toán khác chỉ vì tên đều có chữ “sort”. Phải đọc đúng phương thức và overload đang dùng.

## 6. Chương trình chạy được: view, bản sao và hành vi được bảo đảm

Ví dụ dưới đây dùng public API, không truy cập trường private hay ép kết quả factory về một lớp nội bộ.

Lưu thành `ApiContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ApiContractDemo {
    record Entry(String name, int priority) {}

    public static void main(String[] args) {
        List<String> backing =
                new ArrayList<>(List.of("Ada", "Linus"));
        List<String> view = Collections.unmodifiableList(backing);
        List<String> copy = List.copyOf(backing);

        backing.set(0, "Grace");
        System.out.println("view=" + view);
        System.out.println("copy=" + copy);

        try {
            view.add("Ken");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view.add=UnsupportedOperationException");
        }

        List<String> mutable = new ArrayList<>(copy);
        mutable.add("Ken");
        System.out.println("mutable=" + mutable);

        List<Entry> entries = new ArrayList<>(List.of(
                new Entry("first", 1),
                new Entry("second", 1),
                new Entry("third", 0)));
        Collections.sort(entries, Comparator.comparingInt(Entry::priority));
        System.out.println("stableSort="
                + entries.stream().map(Entry::name).toList());

        Map<String, Integer> counts = new HashMap<>();
        counts.put("z", 1);
        counts.put("a", 2);
        counts.put("m", 3);
        List<String> keys = new ArrayList<>(counts.keySet());
        Collections.sort(keys);
        System.out.println("sortedKeys=" + keys);

        if (args.length > 0 && args[0].equals("--observe")) {
            System.out.println("observedCopyClass=" + copy.getClass().getName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 ApiContractDemo.java
java ApiContractDemo
```

Stdout:

```text
view=[Grace, Linus]
copy=[Ada, Linus]
view.add=UnsupportedOperationException
mutable=[Ada, Linus, Ken]
stableSort=[third, first, second]
sortedKeys=[a, m, z]
```

Các dòng output cố định ở đây dựa vào hợp đồng API đã chọn, không phụ thuộc thứ tự nội bộ của HashMap.

### View không cho sửa khác bản sao không cho sửa

`Collections.unmodifiableList(backing)` tạo một view không cho sửa qua view nhưng vẫn đọc từ danh sách gốc. Vì vậy đổi phần tử trong `backing` được phản ánh khi đọc view.

`List.copyOf(backing)` tạo một danh sách không cho sửa, với các phần tử theo thứ tự nguồn; thay đổi cấu trúc/thay phần tử của nguồn về sau không phản ánh vào bản sao đó. Tài liệu cũng quy định những đặc điểm như không chấp nhận phần tử null và không cho giả định identity của đối tượng trả về. Xem [List.copyOf và Unmodifiable Lists](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

Đây đều là sao chép/giữ tham chiếu phần tử theo hợp đồng của collection, không phải deep copy mọi object. Ví dụ dùng String là phần tử bất biến nên dễ thấy ranh giới. Nếu phần tử là đối tượng mutable, sửa chính đối tượng đó có thể được nhìn thấy từ nhiều danh sách chứa cùng tham chiếu.

### Muốn danh sách có thể sửa thì tạo theo API phù hợp

`new ArrayList<>(copy)` tạo một danh sách mới có thể thêm phần tử. Không cần biết lớp mà `List.copyOf()` đang dùng.

Điều nên viết là “tôi cần một ArrayList có nội dung này”, không phải ép một kết quả chỉ được hứa là List thành ArrayList và hy vọng bản JDK hiện tại trả đúng lớp đó.

### Chủ động xác định thứ tự key

HashMap không hứa một thứ tự duyệt ổn định; tài liệu nói rõ không bảo đảm thứ tự không đổi theo thời gian. Xem [HashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html).

Mẫu sao chép key ra list rồi sắp xếp, nên `sortedKeys=[a, m, z]` được giải thích bởi phép sort. Nó không lấy thứ tự tình cờ của HashMap làm định dạng báo cáo.

Nếu nghiệp vụ cần thứ tự chèn hoặc thứ tự key ngay trong cấu trúc map, phải chọn cấu trúc có hợp đồng thứ tự tương ứng.

## 7. Quan sát tên lớp để chẩn đoán, không dùng làm nhánh nghiệp vụ

Chạy thêm:

```shell
java ApiContractDemo --observe
```

Sau các dòng trên, một lần chạy trên JDK 24 còn in:

```text
observedCopyClass=java.util.ImmutableCollections$List12
```

Đây là quan sát về đối tượng được bản runtime đó chọn cho dữ liệu mẫu. Không yêu cầu máy khác hoặc bản cập nhật khác phải in cùng tên.

Sai lầm về ý tưởng:

```java
if (result.getClass().getName().equals("some.internal.ListClass")) {
    // Suy ra mot hanh vi nghiep vu tu ten lop noi bo.
}
```

Đoạn trên minh họa cách không nên phụ thuộc, không phải một kiểm tra khả năng tương thích. Một lớp nội bộ khác vẫn có thể đáp ứng toàn bộ hợp đồng List.

Tên lớp, source và bytecode có ích khi điều tra một lỗi hoặc hiệu năng. Nếu bài toán phải phụ thuộc một đặc điểm riêng của runtime, cần ghi rõ điều kiện triển khai, cô lập phần phụ thuộc và kiểm tra nó trong môi trường mục tiêu. Không quảng bá kết quả đó như một quy tắc của Java nói chung.

## 8. Cách đọc Javadoc để không trộn các loại thông tin

Khi mở một API, nên xem theo thứ tự:

1. Mô tả lớp/interface và các điều kiện chung.
2. Mô tả đúng phương thức/overload.
3. Tham số, giá trị trả về, ngoại lệ và điều kiện trước/sau.
4. Hợp đồng được kế thừa từ interface hoặc lớp cha.
5. Các phần ghi chú và yêu cầu triển khai, chú ý phạm vi.
6. Mới xem source của đúng bản JDK để giải thích cách nó thực hiện.

Các tiêu đề thường gặp:

| Tiêu đề | Cách đọc |
| --- | --- |
| API Note | Giải thích cách dùng, ví dụ hoặc bối cảnh; không tự biến mọi gợi ý thành một bảo đảm mới |
| Implementation Requirements | Yêu cầu/cách hoạt động được tài liệu nêu cho phần triển khai tương ứng; phải đọc đúng phạm vi, nhất là default method và kế thừa |
| Implementation Note | Thông tin về cách triển khai; không mặc định là ràng buộc cho mọi triển khai thay thế |
| Since | Phiên bản API xuất hiện; không chứng minh mọi chi tiết triển khai đã bất biến từ đó |
| Deprecated | Cần đọc lý do và hướng thay thế; không đồng nghĩa phương thức đã bị xóa ngay |

Không gộp “Implementation Requirements” vào loại có thể bỏ qua. Ví dụ, `Collection.removeIf()` có mô tả công khai cho cách default implementation duyệt và xóa qua iterator; một lớp override có thể thực hiện theo cách phù hợp với lớp đó nhưng vẫn phải giữ hợp đồng cần có. Xem [Collection.removeIf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)).

Nếu method chỉ được khai báo lại với mô tả ngắn, cần xem phần `Specified by`, `Overrides` và hợp đồng ở type cha. Không tìm một câu riêng lẻ rồi bỏ các điều kiện chung ở đầu trang.

## 9. Không có bảo đảm cũng là một thông tin cần sử dụng đúng

Một số API nói rõ giới hạn:

- Thao tác có thể là tùy chọn và có thể ném UnsupportedOperationException.
- Một triển khai không chấp nhận null.
- Hành vi phát hiện sửa đồng thời chỉ là best effort.
- Không bảo đảm thứ tự hoặc identity.
- Một giá trị tổng hợp không phải snapshot nguyên tử.

Ví dụ, tài liệu ArrayList nói cơ chế fail-fast không thể được bảo đảm trong mọi sửa đổi đồng thời không được đồng bộ. Không dùng việc “chắc chắn sẽ ném ConcurrentModificationException” như cơ chế bảo đảm tính đúng đắn cho chương trình nhiều luồng.

Một thuật toán gọi vào API ngoài miền được bảo đảm không được cứu chỉ vì source hiện tại tình cờ xử lý trường hợp đó theo ý muốn.

Mặt khác, cũng không cần né mọi chi tiết được tài liệu công khai. Nếu một lớp cụ thể như ArrayList cam kết đặc tính riêng, ứng dụng có thể dựa vào đặc tính đó khi đã chọn lớp ấy; chỉ không suy rộng nó thành hợp đồng của mọi List.

## 10. Đổi JDK cần kiểm tra những lớp tương thích nào?

Khi chuyển bản/runtime, có thể tách câu hỏi:

| Khía cạnh | Điều cần xác minh |
| --- | --- |
| Mã nguồn | API/ngôn ngữ đang dùng có trong mức hỗ trợ mục tiêu không? |
| Class file | Runtime mục tiêu có chạy được output đã biên dịch không? |
| Hành vi API | Các tiền điều kiện và bảo đảm mà ứng dụng dựa vào có đúng không? |
| Cấu hình/provider | Đặc điểm nào được chọn hoặc thay đổi bởi cấu hình triển khai? |
| Hiệu năng | Thông lượng, độ trễ, bộ nhớ và khởi động thay đổi ra sao? |
| Phụ thuộc nội bộ | Có ép lớp, reflection hoặc tên lớp private nào bị đóng đinh không? |

Tương thích hành vi không tự đồng nghĩa hiệu năng không đổi. Hai triển khai có thể cùng trả kết quả đúng nhưng khác phân bổ bộ nhớ hoặc thời gian chạy.

Ngược lại, một thay đổi số đo không tự chứng minh runtime vi phạm API. Cần kiểm tra liệu đặc tính đó có được hứa hay chỉ là một quan sát của lần triển khai trước.

Dùng đúng tài liệu cho baseline cần hỗ trợ. Ví dụ chương trình trong bài biên dịch với `--release 17`; việc nó nằm trong nội dung định hướng Java 6 không làm `List.copyOf()`, record hay Stream.toList() xuất hiện trên JDK 6.

## 11. Viết kiểm tra dựa vào hợp đồng

Các kiểm tra phù hợp cho ví dụ:

- View phản ánh sự thay đổi nguồn theo hợp đồng backing view.
- Bản sao giữ thứ tự và phần tử nguồn tại lúc copy, không đổi vì nguồn bị thay phần tử về sau.
- Thao tác thêm qua danh sách không cho sửa bị từ chối.
- Thứ tự tương đối của hai Entry cùng priority được giữ sau sort ổn định.
- Báo cáo key có thứ tự vì chương trình chủ động sort.

Các điều không nên cố định như yêu cầu nghiệp vụ:

- Tên lớp nội bộ của copy.
- Số lượng cấp phát chính xác.
- Dung lượng mảng private sau mỗi lần add.
- Thứ tự HashMap khi chưa có bảo đảm tương ứng.
- Thời gian một lời gọi trên máy phát triển.

Chạy qua nhiều JDK/vendor giúp phát hiện phụ thuộc vô tình, nhưng không biến một loạt quan sát giống nhau thành lời hứa của đặc tả. Bằng chứng thực thi và đọc hợp đồng bổ sung cho nhau.

Khi cần ghi một nhận định trong tài liệu kỹ thuật, có thể dùng cách viết rõ phạm vi:

```text
Bảo đảm API: ...
Điều kiện áp dụng: ...
Quan sát trên runtime/version/cấu hình cụ thể: ...
Ứng dụng có phụ thuộc quan sát đó không: ...
```

## 12. Bài tập tự kiểm tra

1. Một phương thức trả List không cho sửa. Vì sao không được ép nó về ArrayList để thêm phần tử? Hãy tạo một bản có thể sửa bằng public API.
2. HashMap hiện in key theo thứ tự tăng dần với vài số nguyên. Hãy giải thích vì sao test yêu cầu thứ tự đó vẫn sai hợp đồng.
3. Một tài liệu nói “sort phải ổn định”, source hiện tại dùng thuật toán X. Phần nào cần giữ khi implementation thay thuật toán?
4. Một lớp override default method có Implementation Requirements. Cần đọc những hợp đồng nào trước khi cho rằng có thể thay tùy ý?
5. Với view và copy trong chương trình, hãy thay phần tử String bằng một object mutable. Tại sao không thể gọi copy nông là deep immutable?
6. Ghi lại tên lớp trả về ở hai môi trường khác nhau nếu có. Chúng khác nhau có đủ để kết luận một bên lỗi không?

Thói quen cần hình thành là tách **điều API hứa**, **điều triển khai chọn** và **điều phép thử quan sát**. Nhờ vậy, mã dựa vào phần đúng để có khả năng chuyển môi trường, còn source và công cụ chẩn đoán được dùng để giải thích từng JDK cụ thể.
