# ConcurrentModificationException và việc sửa collection trong lúc duyệt

## 1. Vì sao một vòng for-each có thể bị lỗi khi xóa?

Một vòng `for-each` trên collection thường làm việc thông qua iterator. Iterator giữ trạng thái của lần duyệt: đang ở đâu, phần tử nào sẽ được trả về tiếp theo và những giả định cần giữ để việc duyệt có ý nghĩa.

Nếu mã thay đổi collection theo cách không được phép trong lần duyệt đó, iterator có thể phát hiện trạng thái không còn phù hợp và ném `ConcurrentModificationException`.

Ví dụ cố ý sai sau dùng `ArrayList`:

```java
for (String name : names) {
    if (name.equals("An")) {
        names.remove(name);
    }
}
```

`names.remove(name)` sửa collection trực tiếp, còn iterator ngầm của `for-each` vẫn đang giữ trạng thái cũ. Việc lỗi được phát hiện thường nằm ở một thao tác duyệt sau đó, nên dòng ném ngoại lệ không nhất thiết là chính lệnh `remove`.

Chữ “Concurrent” trong tên không có nghĩa chắc chắn có hai luồng. Một luồng duy nhất vừa duyệt vừa sửa collection sai hợp đồng cũng có thể gặp ngoại lệ này.

Các cơ chế trong bài vẫn áp dụng trong Java hiện hành. Chương trình minh họa dùng cú pháp chạy bằng JDK 17 trở lên.

## 2. Hiểu đúng fail-fast

Một iterator có cơ chế **fail-fast** cố gắng phát hiện thay đổi không phù hợp và báo lỗi sớm. Với những collection thông dụng như `ArrayList`, thêm/xóa phần tử bên ngoài iterator đang duyệt là nguyên nhân thường gặp.

Nhưng đây không phải cơ chế bảo đảm đồng bộ hay một phép kiểm chứng rằng chương trình đã an toàn:

- Ngoại lệ có thể xuất hiện khi chỉ có một luồng.
- Cơ chế phát hiện hoạt động theo nỗ lực tốt nhất, không phải lời hứa sẽ bắt được mọi thay đổi không hợp lệ.
- Không thấy ngoại lệ trong một lần chạy không chứng minh cách sửa collection là đúng.
- Khi ngoại lệ xảy ra, những thay đổi đã thực hiện trước đó không tự hoàn tác.

Vì vậy không thiết kế chương trình theo hướng “cứ sửa, nếu có ngoại lệ thì thử lại từ đầu”. Cần chọn ngay một cách duyệt và cập nhật có hợp đồng phù hợp.

Tài liệu [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ConcurrentModificationException.html) xác định rõ cả trường hợp một luồng và giới hạn bảo đảm của fail-fast.

### Không phải mọi thay đổi đều giống nhau

Đối với `ArrayList`, thêm hoặc xóa phần tử là thay đổi cấu trúc; thay giá trị tại một vị trí bằng `set` không được phân loại là thay đổi cấu trúc theo cùng nghĩa đó. Sửa trạng thái của đối tượng đang được lưu cũng khác với thêm/xóa phần tử danh sách.

Tuy nhiên, không dùng một quy tắc giản lược như “kích thước không đổi thì chắc mọi iterator đều dùng tiếp được”. Tính hợp lệ còn phụ thuộc thao tác, collection và chính sách iterator cụ thể. Chọn API đúng hợp đồng vẫn quan trọng hơn việc đoán từ kích thước.

Xem định nghĩa thay đổi cấu trúc và chính sách iterator trong [ArrayList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html).

## 3. Xóa khi duyệt: dùng chính iterator đang hoạt động

Nếu cần xem từng phần tử rồi xóa một số phần tử trong một danh sách hỗ trợ thao tác đó, dùng iterator tường minh:

```java
Iterator<String> iterator = names.iterator();
while (iterator.hasNext()) {
    String name = iterator.next();
    if (name.startsWith("A")) {
        iterator.remove();
    }
}
```

Đoạn này cần `import java.util.Iterator;`; `names` là danh sách có thể sửa. `iterator.remove()` xóa phần tử vừa được trả về bởi `next()` qua cơ chế mà chính iterator cung cấp, giúp giữ đúng trạng thái duyệt theo hợp đồng của nó.

Những điều kiện cần nhớ:

1. Phải có lời gọi `next()` phù hợp trước khi xóa.
2. Chỉ gọi `remove()` tối đa một lần cho mỗi phần tử vừa được `next()` trả về; vi phạm thứ tự có thể gây `IllegalStateException`.
3. Iterator phải hỗ trợ `remove`; đây là thao tác tùy chọn và có thể ném `UnsupportedOperationException`.
4. Không đồng thời sửa collection bằng một đường khác rồi kỳ vọng iterator vẫn hợp lệ.

Một iterator thứ hai không được tự động cập nhật chỉ vì iterator thứ nhất đã xóa đúng cách. Quyền sửa của một lần duyệt không biến mọi lần duyệt khác thành cùng một trạng thái.

Tham khảo [Iterator.remove](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html#remove()).

## 4. Chọn cách sửa theo mục tiêu

### 4.1. Chỉ xóa theo điều kiện: removeIf

Với một collection hỗ trợ xóa:

```java
names.removeIf(name -> name.startsWith("A"));
```

Cách viết này trao việc duyệt và xóa cho API của collection, thay vì tự gọi `names.remove(...)` trong một vòng `for-each` đang chạy.

Hàm điều kiện nên chỉ đánh giá phần tử theo yêu cầu. Không đưa những lệnh tự thêm/xóa cùng collection vào bên trong điều kiện rồi cho rằng `removeIf` sẽ xử lý an toàn mọi thay đổi đó.

### 4.2. Thêm hoặc thay phần tử khi duyệt List: ListIterator

`Iterator` thông thường không có thao tác thêm. Với một `List` hỗ trợ chỉnh sửa, có thể dùng `ListIterator.add(...)` để chèn trong lần duyệt và `ListIterator.set(...)` để thay phần tử vừa được trả về theo hợp đồng của iterator.

```java
ListIterator<String> iterator = names.listIterator();
while (iterator.hasNext()) {
    String name = iterator.next();
    if (name.equals("An")) {
        iterator.add("Chi");
    }
}
```

Đoạn này cần `import java.util.ListIterator;`. Với danh sách ban đầu `[An, Binh]`, phần tử `Chi` được chèn sau `An`; con trỏ của iterator đã đứng sau phần tử vừa chèn, nên lượt gọi `next()` tiếp theo đi tới `Binh`, không quay lại duyệt `Chi` vừa thêm.

Vẫn phải kiểm tra danh sách và iterator có hỗ trợ thao tác hay không. Một danh sách không cho sửa không trở thành sửa được chỉ vì dùng `ListIterator`; xem hợp đồng [ListIterator.add](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ListIterator.html#add(E)).

### 4.3. Tách giai đoạn duyệt và cập nhật

Khi muốn thu thập kết quả rồi mới thay đổi collection, có thể giữ phần bổ sung ở danh sách khác:

```java
List<String> additions = new ArrayList<>();
for (String name : names) {
    if (name.startsWith("A")) {
        additions.add(name + "*");
    }
}
names.addAll(additions);
```

Trong lúc duyệt `names`, mã chỉ sửa `additions`; sau khi vòng duyệt kết thúc mới cập nhật `names`. Hai biến phải thật sự đại diện các danh sách khác nhau theo thiết kế, không phải hai tên cùng trỏ tới một danh sách.

Nếu cần xóa sau khi thu thập, phải chọn thao tác đúng ý nghĩa. Chẳng hạn `removeAll` dùng quan hệ so sánh bằng và có thể xóa nhiều phần tử bằng nhau; nó không nhất thiết có cùng ý nghĩa với xóa đúng từng vị trí đã nhìn thấy.

### 4.4. Duyệt bản sao khi cần một tập phần tử đã chụp

Có thể duyệt một danh sách sao chép rồi cập nhật danh sách gốc nếu đó là ý nghĩa thuật toán cần. Việc này có chi phí sao chép và thường chỉ sao chép các tham chiếu phần tử, không sao chép sâu đối tượng.

Tạo bản sao từ một collection đang bị luồng khác sửa không tự là một giao thức đồng bộ an toàn. Cần bảo vệ cả quá trình chụp dữ liệu theo đúng chính sách truy cập, không chỉ đổi cú pháp vòng lặp.

## 5. Chương trình minh họa đầy đủ

Lưu thành `ModificationDuringIterationDemo.java`. Phần đầu cố ý vi phạm hợp đồng để quan sát lỗi; các phần sau minh họa những cách cập nhật có chủ đích.

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.concurrent.CopyOnWriteArrayList;

public class ModificationDuringIterationDemo {
    public static void main(String[] args) {
        List<String> unsafe = new ArrayList<>(List.of("An", "Binh", "Chi"));
        try {
            for (String name : unsafe) {
                if (name.equals("An")) {
                    unsafe.remove(name);
                }
            }
        } catch (ConcurrentModificationException expected) {
            System.out.println("unsafe=ConcurrentModificationException");
        }
        System.out.println("unsafe state=" + unsafe);

        List<String> iteratorRemoval =
                new ArrayList<>(List.of("An", "Binh", "Anh", "Chi"));
        Iterator<String> iterator = iteratorRemoval.iterator();
        while (iterator.hasNext()) {
            String name = iterator.next();
            if (name.startsWith("A")) {
                iterator.remove();
            }
        }
        System.out.println("iterator removal=" + iteratorRemoval);

        List<String> predicateRemoval =
                new ArrayList<>(List.of("An", "Binh", "Anh", "Chi"));
        predicateRemoval.removeIf(name -> name.startsWith("A"));
        System.out.println("removeIf=" + predicateRemoval);

        List<String> inserted = new ArrayList<>(List.of("An", "Binh"));
        ListIterator<String> editing = inserted.listIterator();
        while (editing.hasNext()) {
            String name = editing.next();
            if (name.equals("An")) {
                editing.add("Chi");
            }
        }
        System.out.println("list iterator addition=" + inserted);

        List<String> deferred = new ArrayList<>(List.of("An", "Binh"));
        List<String> additions = new ArrayList<>();
        for (String name : deferred) {
            if (name.startsWith("A")) {
                additions.add(name + "*");
            }
        }
        deferred.addAll(additions);
        System.out.println("after deferred addition=" + deferred);

        CopyOnWriteArrayList<String> snapshotList =
                new CopyOnWriteArrayList<>(List.of("An", "Binh"));
        List<String> seen = new ArrayList<>();
        for (String name : snapshotList) {
            seen.add(name);
            if (name.equals("An")) {
                snapshotList.add("Chi");
            }
        }
        System.out.println("snapshot visited=" + seen);
        System.out.println("snapshot current=" + snapshotList);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror ModificationDuringIterationDemo.java
java ModificationDuringIterationDemo
```

Stdout được kiểm chứng bằng JDK 21:

```text
unsafe=ConcurrentModificationException
unsafe state=[Binh, Chi]
iterator removal=[Binh, Chi]
removeIf=[Binh, Chi]
list iterator addition=[An, Chi, Binh]
after deferred addition=[An, Binh, An*]
snapshot visited=[An, Binh]
snapshot current=[An, Binh, Chi]
```

Trong phần cố ý sai, `An` đã bị xóa trước khi ngoại lệ được phát hiện; collection không tự trở về trạng thái đầu. Khối `catch` chỉ phục vụ minh họa để những phần sau của chương trình vẫn chạy, không phải cách sửa lỗi được khuyến nghị.

Không dùng dòng đầu như một bảo đảm cho mọi collection hoặc mọi lịch thực thi: chính sách phát hiện của fail-fast là giới hạn đã nêu ở mục 2. Những phương án đúng cần được chọn dựa trên hợp đồng, thay vì chờ ngoại lệ xuất hiện.

## 6. Collection đồng thời có chính sách duyệt riêng

Phần cuối dùng `CopyOnWriteArrayList`. Iterator của loại này duyệt một ảnh chụp mảng tham chiếu tại thời điểm iterator được tạo. Vì vậy việc thêm `Chi` không làm `Chi` xuất hiện trong lần duyệt đang chạy; sau vòng lặp, collection hiện tại vẫn có phần tử mới.

Cơ chế ảnh chụp tránh `ConcurrentModificationException` của iterator đó, nhưng có những đánh đổi:

- Những thay đổi sau khi iterator được tạo không được phản ánh trong lần duyệt ấy.
- Các thao tác sửa như thêm/thay có chi phí sao chép mảng, nên không phải lựa chọn mặc định cho dữ liệu bị cập nhật liên tục.
- Chính iterator không hỗ trợ `remove`, `set` hoặc `add` để sửa collection.
- Ảnh chụp các tham chiếu không biến trạng thái bên trong đối tượng phần tử thành bất biến.

Đây là hợp đồng cụ thể của [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html), không phải hành vi chung của mọi collection có tên “concurrent”. Những cấu trúc đồng thời khác có thể dùng chính sách duyệt nhất quán yếu thay vì ảnh chụp.

Nếu dùng nhiều luồng với một collection thông thường, cần giao thức khóa hoặc cấu trúc đồng thời phù hợp với yêu cầu. Chỉ bắt `ConcurrentModificationException` không tạo ra an toàn luồng. Khi dùng một wrapper như [Collections.synchronizedList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)), cũng phải tuân thủ yêu cầu khóa toàn bộ quá trình duyệt; đồng bộ từng thao tác riêng chưa tự bảo vệ một chuỗi lặp. Giữ khóa không hợp thức hóa việc chính luồng đang duyệt gọi thao tác sửa trực tiếp trái hợp đồng iterator.

## 7. Các nguyên nhân khó nhìn thấy

### Thay đổi qua một tham chiếu khác

Mã có thể không gọi `names.remove(...)` ngay trong thân vòng lặp, nhưng một hàm được gọi từ vòng lặp có thể làm điều đó qua cùng tham chiếu collection. Alias, callback hoặc listener có thể khiến việc sửa diễn ra gián tiếp.

Khi truy tìm lỗi, xác định collection mà iterator đang duyệt và mọi đường có thể sửa nó, thay vì chỉ tìm từ khóa `remove` trên một dòng cụ thể.

### Dùng vòng lặp khác như cách né ngoại lệ

Đổi `for-each` thành `forEach(...)`, stream hoặc một iterator khác không tự làm các lệnh sửa bên ngoài trở nên hợp lệ. Cần chọn đúng cơ chế cập nhật theo hợp đồng, không chỉ đổi hình thức duyệt.

Một vòng theo chỉ số cũng cần xử lý chỉ số dịch chuyển khi xóa và đặc điểm hiệu năng của loại danh sách. Không có một cú pháp vòng lặp bảo đảm mọi thuật toán thêm/xóa đều đúng.

### Chỉ thử một dữ liệu nhỏ

Một số cách sửa sai có thể không bị phát hiện trong một lần chạy hoặc có thể kết thúc duyệt trước bước kiểm tra kế tiếp. Không thấy ngoại lệ chưa chứng minh rằng mọi phần tử đã được xử lý đầy đủ, đúng thứ tự hoặc đúng số lần.

Kiểm thử cần kiểm tra kết quả mong muốn và chính sách cập nhật, không chỉ kiểm tra “không có ngoại lệ”.

## 8. Chọn phương án phù hợp

| Nhu cầu | Phương án thường phù hợp |
| --- | --- |
| Duyệt và xóa một số phần tử trong một luồng | `Iterator.remove` được hỗ trợ |
| Xóa theo một điều kiện đơn giản | `removeIf` được hỗ trợ, điều kiện không tự sửa cùng collection |
| Thêm/thay trong khi duyệt List | `ListIterator` với thao tác được hỗ trợ |
| Tính phần bổ sung rồi cập nhật một lần | Thu thập riêng, áp dụng sau vòng duyệt |
| Cần xử lý một ảnh chụp phần tử | Sao chép theo giao thức truy cập phù hợp |
| Nhiều luồng cùng truy cập và cập nhật | Khóa hoặc collection đồng thời với chính sách duyệt đáp ứng yêu cầu |

## 9. Tự kiểm tra

1. `ConcurrentModificationException` có chứng minh có hai luồng đang chạy không?
2. Vì sao `iterator.remove()` khác với `collection.remove(...)` trong cùng lần duyệt?
3. Không có ngoại lệ có đủ chứng minh cách cập nhật là đúng không?
4. Sau khi ngoại lệ được phát hiện, collection có tự hoàn tác những lệnh xóa trước đó không?
5. Vì sao phần tử thêm vào `CopyOnWriteArrayList` không xuất hiện trong vòng duyệt ảnh chụp đã bắt đầu?

Đáp án:

1. Không. Một luồng có thể vi phạm hợp đồng duyệt và gây ngoại lệ.
2. Thao tác của chính iterator tuân theo cơ chế cập nhật trạng thái duyệt mà nó hỗ trợ; sửa trực tiếp collection có thể làm trạng thái iterator không còn hợp lệ.
3. Không. Fail-fast không bảo đảm phát hiện mọi lỗi, và kết quả duyệt vẫn có thể sai.
4. Không. Đây không phải một giao dịch có khả năng rollback tự động.
5. Iterator giữ ảnh chụp đã có ở thời điểm tạo, không đọc lại mảng hiện tại sau mỗi cập nhật.

Hãy thiết kế việc duyệt và cập nhật như một hợp đồng thống nhất: phần tử nào được nhìn thấy, thay đổi được áp dụng lúc nào và API nào cho phép thực hiện thay đổi đó. Ngoại lệ là tín hiệu để tìm lỗi trong hợp đồng ấy.
