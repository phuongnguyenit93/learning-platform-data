# Cơ chế fail-fast và giới hạn bảo đảm của ConcurrentModificationException

Khi đang duyệt một collection, việc thêm hoặc xóa phần tử qua một đường khác có thể làm vị trí mà iterator đang giữ không còn tương ứng với nguồn dữ liệu. Nhiều iterator của các collection thông thường dùng cơ chế **fail-fast** để phát hiện một số thay đổi không phù hợp và ném `ConcurrentModificationException`.

Điểm quan trọng nhất là: **fail-fast là cơ chế hỗ trợ phát hiện lỗi, không phải một cơ chế bảo đảm việc truy cập hoặc duyệt dữ liệu luôn đúng**. Ngoại lệ có thể xuất hiện trong chương trình chỉ có một luồng. Ngược lại, không có ngoại lệ không chứng minh rằng quá trình duyệt không bỏ sót phần tử hoặc rằng truy cập nhiều luồng là an toàn.

Trong bài, viết tắt `CME` chỉ `ConcurrentModificationException`.

## 1. Vấn đề mà fail-fast cố phát hiện

Giả sử một iterator đang duyệt A, B, C:

~~~text
Nguồn lúc tạo iterator: [A, B, C]
Iterator đã lấy: A
Phần dự kiến tiếp theo: B, C
~~~

Một đoạn mã khác xóa B trực tiếp từ danh sách:

~~~text
Nguồn hiện tại: [A, C]
Iterator vẫn mang trạng thái từ lượt duyệt trước thay đổi
~~~

Iterator có thể đang giữ chỉ số, nút, số thay đổi kỳ vọng hoặc thông tin khác của một cấu trúc đã bị đổi. Nếu cứ tiếp tục mà không có chính sách rõ, chương trình có thể bỏ sót, đọc lặp, nhìn thấy dữ liệu không theo kỳ vọng hoặc gặp lỗi.

Fail-fast chọn hướng phát hiện dấu hiệu không còn phù hợp tại một số điểm kiểm tra rồi báo lỗi. Điều đó giúp tìm lỗi sớm hơn trong nhiều tình huống, nhưng không biến iterator thành một ảnh chụp độc lập của nguồn.

## 2. ConcurrentModificationException không đòi hỏi nhiều luồng

Ví dụ chỉ có một luồng:

~~~java
// Đoạn mã trong một phương thức; cần các import java.util tương ứng.
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> iterator = values.iterator();

System.out.println(iterator.next()); // A
values.remove("B"); // Sửa trực tiếp qua List, không qua iterator đang duyệt.

iterator.next(); // Có thể phát hiện thay đổi và ném CME ở triển khai fail-fast.
~~~

Không có `Thread`, executor hay chạy song song. Chính cùng một luồng đã:

1. Tạo iterator.
2. Đi qua một phần dữ liệu.
3. Sửa cấu trúc nguồn qua `values`.
4. Tiếp tục iterator cũ.

Tên “concurrent modification” không chỉ mô tả tình huống có nhiều luồng thực thi cùng lúc. Một luồng cũng có thể vi phạm cách sử dụng nguồn trong khi một lượt duyệt còn đang tồn tại. Tài liệu của [ConcurrentModificationException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html) nêu rõ giới hạn này và việc không được dựa vào ngoại lệ để quyết định tính đúng.

`CME` là ngoại lệ không kiểm tra thuộc nhóm `RuntimeException`. Không có yêu cầu phải bắt nó ở mọi lời gọi iterator.

## 3. Mô hình thường gặp: bộ đếm thay đổi và giá trị kỳ vọng

Trong một triển khai như iterator của `ArrayList`, có thể hình dung:

- Collection giữ bộ đếm thay đổi, thường thấy với tên `modCount`.
- Khi tạo iterator, nó lưu giá trị kỳ vọng, thường thấy với tên `expectedModCount`.
- Một số thao tác của iterator kiểm tra xem hai giá trị còn phù hợp không.
- Nếu phát hiện chênh lệch, iterator ném `CME`.

Mã minh họa ý tưởng:

~~~java
// Mã giả giải thích cơ chế, không phải chương trình độc lập.
void checkForModification() {
    if (collectionVersion != iteratorExpectedVersion) {
        throw new ConcurrentModificationException();
    }
}
~~~

Đây không phải một giao thức API mà mọi collection phải dùng. Không truy cập hoặc sửa các bộ đếm nội bộ từ mã ứng dụng để “sửa” một iterator đã bị vô hiệu hóa.

Một flow đơn giản:

~~~mermaid
flowchart TD
    A["Tạo iterator và lưu phiên bản kỳ vọng"] --> B["Đi tới một thao tác có kiểm tra"]
    B --> C{"Phiên bản nguồn còn phù hợp?"}
    C -->|Có| D["Tiếp tục thao tác duyệt"]
    C -->|Không| E["Ném ConcurrentModificationException"]
    D --> B
~~~

Sơ đồ không nói rằng mọi phương thức đều kiểm tra hoặc rằng việc sửa nguồn tự ném lỗi ngay tại thời điểm sửa.

### Bộ đếm không chỉ là kích thước

Thêm một phần tử rồi xóa chính phần tử đó có thể đưa nội dung và kích thước về như cũ, nhưng đã có những lần sửa cấu trúc từ sau khi iterator được tạo.

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> iterator = values.iterator();

values.add("D");
values.remove("D");

// Nội dung lại là [A, B, C], nhưng iterator không được tự coi là hợp lệ trở lại.
~~~

Chương trình kiểm chứng bên dưới phát hiện thay đổi khi tiếp tục iterator này. Không so sánh `size()` trước–sau để kết luận không hề có thay đổi liên quan đến lượt duyệt.

Cũng không giả định mọi phương thức cập nhật bộ đếm theo đúng một công thức hoặc luôn tăng đúng một đơn vị. Đó là chi tiết triển khai, không phải giao diện kiểm soát phiên bản dành cho ứng dụng.

## 4. Thay đổi cấu trúc và thay giá trị không giống nhau

Với `ArrayList`, thêm/xóa phần tử hoặc thay đổi rõ ràng cấu trúc mảng phía sau là các thay đổi cấu trúc. Chỉ thay một phần tử bằng `set` không được coi là thay đổi cấu trúc theo định nghĩa của lớp. Đồng thời, tài liệu nhấn mạnh fail-fast là nỗ lực phát hiện tốt nhất có thể, không phải bảo đảm tuyệt đối. Xem [ArrayList API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

Bảng cho ngữ cảnh `ArrayList` thông thường:

| Thao tác | Ý nghĩa liên quan đến lượt duyệt |
| --- | --- |
| `list.add(value)` | Có thay đổi cấu trúc nguồn. |
| `list.remove(...)` thực sự xóa phần tử | Có thay đổi cấu trúc nguồn. |
| `list.set(index, value)` | Thay giá trị ở vị trí có sẵn, không thay cấu trúc theo định nghĩa của ArrayList. |
| Sửa thuộc tính của đối tượng nằm trong danh sách | Không tự làm thay đổi cấu trúc danh sách; nội dung đối tượng vẫn có thể đã đổi. |
| Sửa qua iterator khác của cùng nguồn | Vẫn là một đường thay đổi khác đối với iterator hiện tại. |

Trong ví dụ tuần tự:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> iterator = values.iterator();

iterator.next(); // A
values.set(1, "B*");
System.out.println(iterator.next()); // B* với ArrayList trong ví dụ.
~~~

Iterator không phải snapshot bất biến. Không có `CME` sau `set` không có nghĩa iterator vẫn thấy nội dung ban đầu.

Không suy rộng bảng này thành quy tắc “mọi loại collection chỉ có thể vô hiệu iterator khi size thay đổi”. Mỗi loại nguồn có cấu trúc, hợp đồng phương thức và chính sách duyệt riêng.

Đặc biệt, không dùng việc một kiểu sửa đổi không bị bộ đếm phát hiện để kết luận rằng kiểu sửa đổi đó an toàn giữa các luồng hoặc đúng với thuật toán nghiệp vụ đang chạy.

## 5. Vì sao sửa qua chính iterator có thể hợp lệ?

Khi iterator hỗ trợ `remove()`, nó có thể vừa sửa nguồn vừa điều chỉnh trạng thái duyệt và phiên bản kỳ vọng của chính nó:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
Iterator<String> iterator = values.iterator();

while (iterator.hasNext()) {
    String value = iterator.next();
    if (value.equals("B")) {
        iterator.remove();
    }
}

System.out.println(values); // [A, C]
~~~

Không thay `iterator.remove()` thành `values.remove(value)` rồi cho rằng hai đường thao tác tương đương.

Một `ListIterator` hỗ trợ chỉnh sửa còn có `add` và `set` với các quy tắc trạng thái riêng. Việc chỉnh sửa được phép này phải đi qua **chính bộ duyệt đang được dùng**, trong đúng điều kiện và trên nguồn có hỗ trợ.

### Một iterator hợp lệ không bảo vệ mọi iterator khác

Nếu có hai iterator `first` và `second` trên cùng một ArrayList, `first.remove()` có thể cập nhật đúng trạng thái của first. Nhưng second không vì vậy mà tự được cập nhật tất cả trạng thái kỳ vọng.

Tương tự, việc một danh sách được sửa đúng cách ở một đoạn mã không tự hợp thức hóa những iterator cũ còn giữ ở nơi khác.

Đây là lý do cần xác định vòng đời và quyền sửa nguồn của từng lượt duyệt, thay vì chỉ tìm xem “ở đâu đó đã dùng iterator.remove hay chưa”.

## 6. Fail-fast không có nghĩa kiểm tra ở mọi lời gọi

Iterator có thể kiểm tra tại `next()`, `remove()`, một số bước của `forEachRemaining` hoặc các điểm khác. Không có quy tắc chung rằng `hasNext()` luôn kiểm tra đầy đủ mọi thay đổi.

Với bản OpenJDK 24.0.2 dùng để chạy ví dụ bài này, kiểm tra bytecode của `ArrayList$Itr` cho thấy:

- `hasNext()` so vị trí con trỏ với kích thước hiện tại.
- `next()` gọi kiểm tra thay đổi trước khi lấy dữ liệu.

Có thể tự xem trên JDK đang dùng:

~~~shell
javap -c -p 'java.util.ArrayList$Itr'
~~~

Tên lớp nội bộ và chi tiết bytecode chỉ phục vụ tìm hiểu phiên bản đang chạy. Mã ứng dụng không nên dựa vào chúng để chọn những đường sửa nguồn “né được kiểm tra”.

### Ví dụ có thể bỏ sót mà không có CME

~~~java
List<String> values = new ArrayList<>(List.of("A", "B"));
List<String> visited = new ArrayList<>();

for (String value : values) {
    visited.add(value);
    if (value.equals("A")) {
        values.remove(value);
    }
}
~~~

Trong lần chạy kiểm chứng của bài:

~~~text
visited = [A]
values  = [B]
Không có CME
~~~

Diễn biến ở triển khai được quan sát:

1. Iterator lấy A, con trỏ tiến đến vị trí `1`.
2. Xóa A trực tiếp làm danh sách còn B ở vị trí `0`, size là `1`.
3. `hasNext()` so con trỏ `1` với size `1`, nên kết thúc.
4. Không gọi `next()` nữa để chạm điểm phát hiện phiên bản đã lệch.

B còn trong danh sách nhưng không được đưa vào `visited`.

Đây là minh họa giới hạn phát hiện, không phải hành vi hợp lệ để ứng dụng khai thác. Không viết logic cần “vòng này sẽ im lặng bỏ qua phần tử” hoặc kiểm thử đa nền tảng ép mọi JDK phải cho đúng hiện tượng này.

## 7. Best-effort: giới hạn bảo đảm cần hiểu

“Nỗ lực phát hiện tốt nhất có thể” trong ngữ cảnh fail-fast có các hệ quả:

- Một dấu hiệu thay đổi bị phát hiện có thể làm lượt duyệt thất bại.
- Không có cam kết mọi sửa đổi sai đều được phát hiện.
- Không có cam kết ngoại lệ xuất hiện đúng tại lệnh sửa nguồn.
- Không có cam kết mọi phương thức iterator kiểm tra ở cùng một điểm giữa các phiên bản.
- Không có cam kết không ném lỗi nghĩa là có một ảnh chụp dữ liệu nhất quán.

Trong tình huống nhiều luồng không đồng bộ, còn có vấn đề nhìn thấy dữ liệu và thứ tự thực thi. Một bộ đếm phát hiện sửa đổi không tự cung cấp khóa, thao tác nguyên tử, quan hệ đồng bộ hoặc một giao dịch đọc.

Ngay cả nếu đổi một trường quan sát thành `volatile` ở một thiết kế riêng, việc thấy bộ đếm mới cũng không tự biến cả chuỗi “kiểm tra rồi lấy phần tử” thành một thao tác nguyên tử. Bài toán đồng bộ phải được thiết kế ở cấp phù hợp.

Đừng xây tính đúng của chương trình theo mô hình:

~~~text
Có CME -> dữ liệu không an toàn
Không có CME -> dữ liệu an toàn
~~~

Không có nhánh thứ hai như một bảo đảm chung.

## 8. Fail-fast không hoàn tác công việc đã thực hiện

Trong ví dụ xóa B sau khi đã xử lý A, lỗi có thể chỉ xảy ra ở lời gọi iterator tiếp theo. Trước thời điểm đó:

- Hành động với A có thể đã chạy.
- Danh sách có thể đã bị thay đổi.
- Log, bộ đếm, tệp hoặc tác vụ bên ngoài có thể đã được ghi.

Bắt `CME` không khôi phục dữ liệu nguồn hay hoàn tác những tác động đó.

Không dùng cách bắt rồi bỏ qua:

~~~java
// Ý tưởng không đủ để bảo đảm thuật toán đúng.
try {
    // Duyệt và thực hiện công việc.
} catch (ConcurrentModificationException exception) {
    // Bỏ qua lỗi không chứng minh mọi phần tử đã được xử lý.
}
~~~

Cũng không tự động chạy lại toàn bộ vòng lặp chỉ vì bắt được CME. Nếu lần trước đã gửi thông báo cho A, lần thử lại có thể gửi A thêm một lần nữa; đồng thời dữ liệu nguồn có thể tiếp tục thay đổi.

Chỉ retry khi đã có một thiết kế phù hợp về quyền sở hữu dữ liệu, ảnh chụp, tính lặp an toàn và checkpoint nghiệp vụ. Trong nhiều lỗi một luồng, cách sửa đúng đơn giản là thay đường chỉnh sửa nguồn hoặc tách giai đoạn đọc và cập nhật.

## 9. Các đường sửa nguồn khó nhìn thấy

Không chỉ lời gọi `values.add/remove` ngay trong thân vòng lặp mới có liên quan.

### Alias cùng đối tượng

Hai biến có tên khác nhau có thể cùng trỏ một collection:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
List<String> alias = values;
Iterator<String> iterator = values.iterator();

alias.remove("B"); // Vẫn sửa đúng nguồn mà iterator đang dùng.
~~~

Đổi tên biến không tạo bản sao hoặc ranh giới sở hữu mới.

### View và collection phía sau

Các góc nhìn như `subList`, `keySet`, `values` hoặc `entrySet` có thể liên hệ với nguồn phía sau. Sửa qua một đường có thể ảnh hưởng lượt duyệt ở một đường khác, theo hợp đồng của loại nguồn cụ thể.

Không tự coi một view là một snapshot độc lập. Với ArrayList, thay cấu trúc danh sách cha trong lúc còn dùng một subList cũng có những giới hạn hợp đồng cần xem xét, không chỉ lỗi của một iterator riêng.

### Callback hoặc lời gọi lồng nhau

Thân vòng lặp có thể chỉ gọi:

~~~java
process(value);
~~~

nhưng `process` lại sửa collection nguồn, hoặc phát sự kiện tới một đoạn mã sửa nó. Khi điều tra, phải lần theo các đường ghi thực tế, không chỉ tìm chữ `remove` ở cùng một phương thức.

### Góc nhìn không cho sửa không phải snapshot

`Collections.unmodifiableList(backing)` chặn thay đổi qua góc nhìn đó. Nếu nơi khác vẫn giữ và sửa `backing`, dữ liệu và iterator của góc nhìn không tự trở thành một bản sao bất biến.

Giữ một lớp bao bọc chỉ đọc khác với tạo một dữ liệu độc lập để duyệt.

## 10. Chọn cách xử lý đúng cho một luồng

| Nhu cầu | Cách xử lý thường phù hợp |
| --- | --- |
| Xóa phần tử thỏa điều kiện trong nguồn có thể sửa | `removeIf`, hoặc vòng lặp với `iterator.remove` nếu được hỗ trợ. |
| Vừa duyệt List vừa chèn/thay/xóa ở vị trí duyệt | `ListIterator` với thứ tự thao tác hợp lệ. |
| Giữ nguyên nguồn và tạo dữ liệu đã lọc | Tạo collection kết quả mới. |
| Cần thêm nhiều phần tử sau khi duyệt nguồn | Thu vào một collection phụ rồi thêm ở giai đoạn sau. |
| Cần đọc một trạng thái cố định | Chụp dữ liệu theo một quy trình phù hợp, rồi duyệt bản chụp. |

Ví dụ xóa bằng điều kiện:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
values.removeIf(value -> value.equals("B"));

System.out.println(values); // [A, C]
~~~

Đừng tự sửa chính nguồn trong predicate của `removeIf`. Dùng API chuyên dụng không có nghĩa callback được quyền thực hiện mọi thay đổi khác lên collection đang được xử lý.

Nếu chỉ sửa vòng lặp thành duyệt theo chỉ số để không còn iterator, chương trình có thể không còn gặp cùng ngoại lệ. Nhưng logic vẫn có thể bỏ sót vì chỉ số bị dịch, và truy cập nhiều luồng vẫn chưa được giải quyết. Mục tiêu là đúng thuật toán, không phải biến mất thông báo lỗi.

## 11. Khi nhiều luồng: khóa phải bảo vệ cả lượt duyệt

`ArrayList` không tự cung cấp đồng bộ cho việc nhiều luồng cùng truy cập và sửa cấu trúc. Một lựa chọn là bao bọc bằng `Collections.synchronizedList`, nhưng khi duyệt cần giữ khóa đúng phạm vi và mọi đường truy cập nguồn phải theo cùng giao thức. Xem [Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

~~~java
// Minh họa một phần thiết kế; cần các import java.util tương ứng.
List<String> shared =
        Collections.synchronizedList(new ArrayList<>());

// Các đoạn mã khác cũng phải truy cập qua shared theo quy tắc đồng bộ phù hợp.
synchronized (shared) {
    Iterator<String> iterator = shared.iterator();
    while (iterator.hasNext()) {
        String value = iterator.next();
        System.out.println(value);
    }
}
~~~

Chỉ khóa lúc tạo iterator rồi nhả trước vòng lặp không bảo vệ toàn bộ lượt duyệt.

Chỉ khóa từng lời gọi `hasNext` và `next` riêng lẻ cũng không tương đương giữ một khóa xuyên suốt nếu thuật toán cần một lượt đọc không bị xen thay đổi.

Ngay cả đang giữ khóa, chính luồng đó vẫn có thể sửa nguồn sai cách trong thân vòng lặp và làm iterator mất hiệu lực. Khóa giải quyết việc xen kẽ truy cập theo giao thức; nó không bỏ quy tắc trạng thái của iterator.

### Chụp nhanh trong khóa rồi xử lý ngoài khóa

Nếu phần xử lý lâu và chỉ cần nội dung ở thời điểm chụp:

~~~java
List<String> snapshot;
synchronized (shared) {
    snapshot = new ArrayList<>(shared);
}

for (String value : snapshot) {
    System.out.println(value);
}
~~~

Bản chụp độc lập về cấu trúc danh sách, nhưng là bản sao nông: các đối tượng phần tử vẫn có thể được chia sẻ. Cần xác định chính sách cho nội dung có thể thay đổi bên trong phần tử.

Cũng không tạo snapshot của một ArrayList đang bị luồng khác sửa mà không có giao thức phù hợp rồi cho rằng thao tác copy tự bảo đảm một ảnh chụp nhất quán.

## 12. Các chính sách iterator khác với fail-fast

Không phải mọi iterator đều chọn cách phát hiện rồi ném CME.

| Chính sách | Ví dụ | Điều cần hiểu |
| --- | --- | --- |
| Fail-fast | Iterator của nhiều collection thông thường như ArrayList | Hỗ trợ phát hiện sửa đổi không phù hợp, theo nỗ lực tốt nhất có thể. |
| Ảnh chụp tại thời điểm tạo iterator | Iterator của CopyOnWriteArrayList | Duyệt trạng thái mà iterator đã chụp; không cập nhật thành viên theo các thay đổi cấu trúc sau đó. |
| Nhất quán yếu (weakly consistent) | Iterator của ConcurrentHashMap | Có thể hoạt động trong lúc cập nhật theo chính sách của nguồn; không phải một snapshot toàn bộ map tại một thời điểm chung. |

Iterator của [CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html) giữ một ảnh chụp cấu trúc khi được tạo; các thao tác thay đổi qua iterator như remove không được hỗ trợ. Cơ chế này có chi phí ghi và bộ nhớ cần cân nhắc, không phải giải pháp mặc định cho mọi danh sách.

Ví dụ:

~~~text
Nguồn lúc tạo iterator: [A, B]
Sau đó nguồn thêm C và xóa A: [B, C]
Iterator ảnh chụp vẫn duyệt: [A, B]
~~~

Ảnh chụp là về tập các tham chiếu phần tử của lượt duyệt, không tự sao chép sâu toàn bộ đối tượng.

Iterator của [ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) không ném CME theo chính sách của nó. Điều đó không có nghĩa một lượt duyệt cho ảnh chụp giao dịch của toàn bộ map, và bản thân một iterator không phải đối tượng để tùy ý chia sẻ giữa nhiều luồng cùng điều khiển con trỏ.

Không gom các loại này thành một nhãn “fail-safe” rồi mặc nhiên suy ra mọi bảo đảm về nhìn thấy cập nhật, snapshot, thao tác ghi hoặc đồng bộ đều giống nhau. Hãy dùng đúng mô tả chính sách của lớp cụ thể.

## 13. Chương trình kiểm chứng hoàn chỉnh

Lưu thành **FailFastLimitsDemo.java**.

Mã dùng API có từ Java 17. Những đoạn cố ý vi phạm lượt duyệt là **thí nghiệm quan sát**, không phải mã ứng dụng mẫu cần dùng. Kết quả quan sát dưới đây được kiểm chứng trên OpenJDK 24.0.2; đặc biệt hiện tượng vòng lặp sai nhưng không ném CME là chi tiết cần quan sát lại khi đổi triển khai.

Không dùng một hiện tượng không được bảo đảm làm yêu cầu hành vi đa phiên bản.

~~~java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class FailFastLimitsDemo {
    public static void main(String[] args) {
        System.out.println("Runtime feature = " + Runtime.version().feature());
        directModification();
        sameSizeAfterTwoChanges();
        nonStructuralReplacement();
        skippedWithoutException();
        safeIteratorRemoval();
        safeRemoveIf();
        snapshotIteration();
    }

    private static void directModification() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> iterator = values.iterator();
        System.out.println("Direct edit first = " + iterator.next());
        values.remove("B");
        try {
            System.out.println("Direct edit next = " + iterator.next());
        } catch (ConcurrentModificationException exception) {
            System.out.println("Direct edit detected = "
                    + exception.getClass().getSimpleName());
        }
        System.out.println("After detected edit = " + values);
    }

    private static void sameSizeAfterTwoChanges() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> iterator = values.iterator();
        values.add("D");
        values.remove("D");
        System.out.println("Same contents restored = " + values);
        try {
            iterator.next();
            System.out.println("Restored contents detected = false");
        } catch (ConcurrentModificationException exception) {
            System.out.println("Restored contents detected = true");
        }
    }

    private static void nonStructuralReplacement() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> iterator = values.iterator();
        iterator.next();
        values.set(1, "B*");
        System.out.println("Next after ArrayList.set = " + iterator.next());
    }

    private static void skippedWithoutException() {
        List<String> values = new ArrayList<>(List.of("A", "B"));
        List<String> visited = new ArrayList<>();
        boolean detected = false;
        try {
            for (String value : values) {
                visited.add(value);
                if (value.equals("A")) {
                    values.remove(value);
                }
            }
        } catch (ConcurrentModificationException exception) {
            detected = true;
        }
        System.out.println("Short loop visited = " + visited);
        System.out.println("Short loop remaining = " + values);
        System.out.println("Short loop detected = " + detected);
    }

    private static void safeIteratorRemoval() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        Iterator<String> iterator = values.iterator();
        while (iterator.hasNext()) {
            String value = iterator.next();
            if (value.equals("B")) {
                iterator.remove();
            }
        }
        System.out.println("Iterator removal = " + values);
    }

    private static void safeRemoveIf() {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        values.removeIf(value -> value.equals("B"));
        System.out.println("removeIf = " + values);
    }

    private static void snapshotIteration() {
        CopyOnWriteArrayList<String> values =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> snapshot = values.iterator();
        values.add("C");
        values.remove("A");

        List<String> observed = new ArrayList<>();
        snapshot.forEachRemaining(observed::add);
        System.out.println("Snapshot observed = " + observed);
        System.out.println("Copy-on-write current = " + values);
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 FailFastLimitsDemo.java
java FailFastLimitsDemo
~~~

`--release 17` kiểm tra mức ngôn ngữ/API đích khi biên dịch; nó không biến JVM chạy chương trình thành Java 17.

Stdout trong lần chạy kiểm chứng trên OpenJDK 24.0.2:

~~~text
Runtime feature = 24
Direct edit first = A
Direct edit detected = ConcurrentModificationException
After detected edit = [A, C]
Same contents restored = [A, B, C]
Restored contents detected = true
Next after ArrayList.set = B*
Short loop visited = [A]
Short loop remaining = [B]
Short loop detected = false
Iterator removal = [A, C]
removeIf = [A, C]
Snapshot observed = [A, B]
Copy-on-write current = [B, C]
~~~

### Đọc bằng chứng theo đúng giới hạn

**Direct edit**

A đã được lấy, rồi xóa B trực tiếp. Lần next tiếp theo phát hiện thay đổi. Danh sách đã thành A, C trước lúc ngoại lệ được báo; ngoại lệ không hoàn tác việc xóa B.

**Same contents restored**

Thêm D rồi xóa D đưa nội dung về A, B, C. Iterator tạo trước hai thay đổi vẫn bị phát hiện không còn phù hợp. Kích thước hoặc nội dung cuối cùng không thể thay cho lịch sử thay đổi liên quan đến iterator.

**ArrayList.set**

Thay B bằng B* không đổi cấu trúc theo chính sách của ArrayList. Lần next tuần tự quan sát B*, thể hiện iterator không giữ bản sao ban đầu của các phần tử.

**Short loop**

Chỉ A được đưa vào visited, B còn lại trong nguồn, và không có CME trong lần chạy này. Đây là bằng chứng cụ thể rằng không ném ngoại lệ không đồng nghĩa thuật toán đã duyệt đủ.

**Iterator removal và removeIf**

Hai cách được dùng theo hợp đồng trên ArrayList có thể sửa nguồn và cho A, C như mong muốn. Chúng không dựa vào việc một lỗi fail-fast có xuất hiện hay không.

**Copy-on-write snapshot**

Iterator được tạo khi nguồn có A, B. Nguồn sau đó thành B, C nhưng iterator vẫn thu được A, B theo chính sách ảnh chụp. Đây là chính sách khác với fail-fast, không phải fail-fast “không hoạt động”.

Chương trình không có lịch chạy nhiều luồng ngẫu nhiên. Nhờ vậy các ví dụ tách được lỗi dùng iterator trong một luồng khỏi vấn đề đồng bộ. Khi học truy cập đồng thời, cần kiểm thử các bảo đảm tương ứng của thiết kế riêng, không dùng xác suất xuất hiện CME làm thước đo.

## 14. Cách điều tra khi gặp CME

1. **Xác định nguồn thực tế:** ArrayList, HashMap, một view, một lớp bao bọc hay cấu trúc concurrent?
2. **Xác định lúc iterator được tạo:** có được giữ qua nhiều giai đoạn, callback hoặc lời gọi khác không?
3. **Tìm mọi đường ghi:** biến alias, danh sách cha, view, callback, listener, luồng khác.
4. **Đối chiếu chính sách:** thao tác thay đổi có được thực hiện qua đúng iterator đang duyệt và được hỗ trợ không?
5. **Xem công việc đã chạy trước lỗi:** có tác động nào cần xử lý hoặc tránh lặp lại khi sửa không?
6. **Chọn mô hình đúng:** sửa qua iterator, tách giai đoạn, chụp dữ liệu, khóa đúng phạm vi hoặc dùng cấu trúc concurrent phù hợp.

Stack trace thường chỉ điểm nơi iterator **phát hiện** bất nhất, không nhất thiết trỏ trực tiếp vào lệnh đã sửa nguồn. Vì vậy chỉ sửa dòng đang ném mà không lần theo đường ghi có thể che lỗi mà không giải quyết nguyên nhân.

Sau khi sửa, kiểm tra nội dung kết quả, số lượng phần tử được xử lý, số lần tác động và chính sách nhìn thấy cập nhật. Đừng dừng ở việc “chạy không còn ngoại lệ”.

## 15. Kiểm thử và lỗi thường gặp

Các ca cần có:

- Sửa trực tiếp trong cùng luồng sau khi đã tạo iterator.
- Sửa qua alias hoặc collection phía sau một view.
- Xóa phần tử đầu, giữa và gần cuối trong các danh sách có kích thước khác nhau.
- Thêm rồi xóa để nội dung cuối trở lại như cũ.
- Dùng iterator.remove đúng điều kiện.
- Hai iterator cùng nguồn nhưng chỉ một iterator thực hiện thay đổi.
- Chụp dữ liệu và kiểm tra đúng chính sách nhìn thấy trạng thái cũ.
- Các đường ghi và đọc đồng thời theo giao thức được thiết kế.

Một ca thí nghiệm có thể ghi nhận CME để minh họa. Nhưng kiểm thử tính đúng của mã ứng dụng phải kiểm tra các bất biến nghiệp vụ và kết quả. Không yêu cầu một lỗi dùng sai nguồn luôn phải ném CME tại đúng dòng trên mọi phiên bản Java.

| Hiểu nhầm | Cách hiểu cần giữ |
| --- | --- |
| CME chỉ do nhiều luồng | Một luồng sửa nguồn trong lúc còn dùng iterator cũng có thể gây lỗi. |
| Sửa nguồn là ném ngay lập tức | Thường lỗi được phát hiện tại điểm kiểm tra của lượt duyệt sau đó. |
| hasNext luôn kiểm tra bộ đếm | Điểm kiểm tra tùy triển khai; không dựa vào giả định này. |
| Không có CME thì đã duyệt đủ | Có thể bỏ sót hoặc có quan sát không đúng mà không ném lỗi. |
| Size cuối không đổi thì iterator còn hợp lệ | Những lần sửa cấu trúc vẫn có thể đã làm phiên bản kỳ vọng lệch. |
| set không gây CME nên tự an toàn nhiều luồng | Không đổi cấu trúc không đồng nghĩa có đồng bộ hoặc snapshot. |
| Bắt rồi retry là cách sửa chung | Công việc đã thực hiện có thể bị lặp, còn nguồn vẫn tiếp tục thay đổi. |
| Synchronized wrapper tự khóa cả vòng lặp | Cần bảo vệ đúng phạm vi duyệt theo hợp đồng và mọi đường truy cập. |
| Cấu trúc concurrent luôn cho snapshot toàn bộ | Chính sách weakly consistent khác với snapshot. |
| Đổi sang vòng lặp chỉ số là xong | Có thể vẫn sai về dịch chỉ số, bỏ sót và truy cập đồng thời. |

## 16. Thực hành

1. Chạy chương trình mẫu trên JDK đang dùng và ghi rõ phiên bản. Phân biệt kết quả quan sát với các cam kết API.
2. Thay danh sách hai phần tử trong `skippedWithoutException` bằng ba hoặc bốn phần tử. Không đặt trước yêu cầu “phải luôn ném”; hãy kiểm tra những phần tử thực sự được duyệt.
3. Sửa ví dụ xóa trực tiếp thành iterator.remove, rồi thành removeIf. Kiểm chứng kết quả thay vì chỉ kiểm chứng không có ngoại lệ.
4. Tạo hai biến trỏ cùng danh sách và sửa qua biến còn lại. Giải thích vì sao iterator vẫn liên quan đến cùng nguồn.
5. Thiết kế một lượt đọc cần ảnh chụp nhất quán và một lượt theo dõi chấp nhận cập nhật trong khi duyệt. Chọn chính sách dữ liệu cho từng trường hợp.
6. Với một vòng lặp có gửi thông báo, phân tích nguy cơ nếu bắt CME rồi chạy lại từ đầu. Xác định cần giữ bằng chứng xử lý hoặc tính lặp an toàn ở đâu.

CME cho biết một dấu hiệu sử dụng collection không phù hợp đã được phát hiện. Tính đúng phải đến từ quyền sở hữu nguồn, cách chỉnh sửa, chính sách duyệt và giao thức đồng bộ; việc có hay không có ngoại lệ chỉ là một phần bằng chứng khi tìm lỗi.
