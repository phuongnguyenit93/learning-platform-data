# Chèn nhiều phần tử bằng addAll có vị trí

Khi cần chèn một nhóm phần tử vào giữa danh sách, `List.addAll(index, source)` biểu đạt trực tiếp ý định: đặt toàn bộ nhóm vào một vị trí, giữ thứ tự mà nguồn cung cấp, rồi đẩy phần đuôi của danh sách đích sang phải.

Ví dụ:

~~~text
Đích ban đầu: [A, D]
Nhóm chèn:   [B, C]
Vị trí:      1

Kết quả:     [A, B, C, D]
~~~

Đây là **chèn thêm**, không phải thay thế hai phần tử và cũng không phải chuyển nhóm khỏi nguồn. Với nguồn và đích độc lập, nhóm nguồn vẫn còn sau thao tác.

Bài dùng các ví dụ Java 17 trở lên và chủ yếu dùng ArrayList có thể thay đổi để nhìn rõ kết quả.

## 1. Chữ ký và ba vai trò cần phân biệt

Chữ ký trong `List<E>`:

~~~java
boolean addAll(int index, Collection<? extends E> source)
~~~

Đây là chữ ký để đọc hiểu, không phải phương thức cần tự cài đặt khi chỉ sử dụng List.

- Đối tượng nhận lời gọi là **danh sách đích**.
- `index` là vị trí trong đích mà phần tử đầu tiên của nhóm sẽ nhận.
- `source` là collection cung cấp các phần tử của nhóm.
- Giá trị trả về cho biết đích có thay đổi do lời gọi hay không, không phải số phần tử được thêm.

Ví dụ:

~~~java
// Đoạn mã trong một phương thức; cần các import java.util tương ứng.
List<String> destination = new ArrayList<>(List.of("A", "D"));
List<String> source = List.of("B", "C");

boolean changed = destination.addAll(1, source);

System.out.println(changed);     // true
System.out.println(destination); // [A, B, C, D]
~~~

Nguồn không nhất thiết là List; tham số nhận một `Collection` phù hợp. Một `Set` cũng có thể cung cấp phần tử, nhưng quy tắc thứ tự của nguồn vẫn phải được hiểu rõ.

Một `Iterable` tùy ý hoặc một `Stream` không tự trở thành `Collection` chỉ vì có thể tạo ra các phần tử. Nếu API đầu vào không phải Collection, cần chọn một cách thu thập hoặc duyệt phù hợp trước khi dùng overload này.

Hợp đồng về vị trí, thứ tự nguồn và nguồn bị thay đổi trong khi thực hiện có tại [List.addAll trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#addAll(int,java.util.Collection)).

## 2. Vị trí chèn: từ 0 đến size, bao gồm cả size

Với danh sách đích có `n` phần tử:

~~~text
0 <= index <= n
~~~

là miền vị trí chèn hợp lệ.

Ví dụ đích A, D có size `2`:

~~~text
Vị trí: 0   1   2
        | A | D |
~~~

- `index == 0`: chèn trước A.
- `index == 1`: chèn giữa A và D.
- `index == 2`: chèn sau D, tức thêm cuối.

Không nhầm với get hoặc set: hai phương thức đó cần một phần tử đã có nên chỉ số phải nhỏ hơn size. addAll chèn tại một khoảng trống, nên được phép bằng size.

### Đầu danh sách

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));
destination.addAll(0, List.of("H1", "H2"));

System.out.println(destination); // [H1, H2, A, D]
~~~

Cả nhóm H1, H2 đứng đầu theo đúng thứ tự nguồn.

### Cuối danh sách

~~~java
destination.addAll(destination.size(), List.of("T1", "T2"));
~~~

Nhóm được đặt ở cuối. Không có phần tử cũ nào phía sau điểm chèn để đổi chỉ số.

Về nội dung dãy khi thao tác được hỗ trợ, `destination.addAll(source)` là dạng thêm cuối; overload có chỉ số cho phép chọn vị trí khác thay vì chỉ cuối.

### Đích rỗng

~~~java
List<String> destination = new ArrayList<>();
destination.addAll(0, List.of("first", "second"));

System.out.println(destination); // [first, second]
~~~

Khi đích rỗng, `0` là vị trí chèn duy nhất hợp lệ. Capacity được dự trữ trong một ArrayList không làm xuất hiện những vị trí công khai khác khi size vẫn bằng `0`.

## 3. Mô hình phần đầu – nhóm mới – phần đuôi

Gọi:

- `n`: size đích trước thao tác.
- `p`: vị trí chèn.
- `m`: số phần tử trong nguồn ổn định của lần thao tác.

Khi thành công, có thể đọc kết quả theo dạng:

~~~text
đích cũ [0, p)
    + các phần tử nguồn theo thứ tự duyệt
    + đích cũ [p, n)
~~~

Ví dụ:

~~~text
Đích:   [A, B, E, F]
p = 2
Nguồn:  [C, D]
m = 2

Phần đầu: [A, B]
Nhóm mới: [C, D]
Phần đuôi:[E, F]

Kết quả: [A, B, C, D, E, F]
~~~

Các vị trí thay đổi:

| Nhóm | Vị trí sau chèn |
| --- | --- |
| Phần tử đích cũ ở j < p | Giữ vị trí j |
| Phần tử thứ k của nguồn, k bắt đầu từ 0 | Nhận vị trí p + k |
| Phần tử đích cũ ở j >= p | Chuyển sang j + m |

Size mới là `n + m` nếu toàn bộ nhóm đã được chèn thành công.

Thứ tự tương đối giữa các phần tử đích cũ không bị đảo. E vẫn đứng trước F. Thứ tự của nhóm nguồn cũng không bị đảo: C đứng trước D.

### Đây là chèn, không phải ghi đè

Nếu dùng set để thay các vị trí từ p, ta đang viết một thuật toán khác, có thể mất các phần tử cũ hoặc vượt miền khi chưa có đủ vị trí.

`addAll` giữ phần đuôi cũ bằng cách tạo chỗ cho nhóm mới. Không cần tự xóa, tự giữ lại phần đuôi rồi gắn vào chỉ để thực hiện một phép chèn thông thường.

## 4. Thứ tự nhóm đến từ iterator của nguồn

addAll không tự sắp xếp các phần tử.

Với:

~~~java
List<String> source = List.of("C", "B");
~~~

nhóm chèn là C rồi B, không phải B rồi C.

Với nguồn có thứ tự chèn rõ ràng:

~~~java
LinkedHashSet<String> source =
        new LinkedHashSet<>(List.of("C", "B", "C"));

List<String> destination = new ArrayList<>(List.of("A", "D"));
destination.addAll(1, source);

System.out.println(destination); // [A, C, B, D]
~~~

Nguồn Set đã loại lần xuất hiện C lặp theo hợp đồng của nó. Danh sách đích nhận C rồi B theo thứ tự mà nguồn cung cấp.

Nếu nguồn là HashSet, không dựa vào một thứ tự duyệt cụ thể tình cờ quan sát được. Việc đích là ArrayList không tự khôi phục lịch sử chèn hoặc sắp nguồn theo thứ tự tự nhiên.

Nếu cần một quy tắc hiển thị rõ:

~~~java
// source là Collection<String> đã có; giả định không có null.
List<String> orderedBatch = new ArrayList<>(source);
orderedBatch.sort(Comparator.naturalOrder());

destination.addAll(position, orderedBatch);
~~~

Đoạn mã này chủ động chọn thứ tự tự nhiên cho khóa String. Đó là quyết định bổ sung trước khi chèn, không phải hành vi mặc định của addAll.

### Nguồn List có phần tử lặp

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));
destination.addAll(1, List.of("B", "B"));

System.out.println(destination); // [A, B, B, D]
~~~

Trong ArrayList này, hai lần xuất hiện B đều được thêm. Giá trị đã có trong đích hoặc lặp trong nguồn không làm addAll tự trở thành phép hợp tập hợp.

Với một lớp List chuyên biệt có giới hạn phần tử riêng, cần xem hợp đồng cụ thể. Không suy ra mọi lớp mang kiểu List đều cho mọi dữ liệu mà một ArrayList cho phép.

## 5. Boolean trả về và nguồn rỗng

Với ArrayList có thể sửa:

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));

boolean changed = destination.addAll(1, List.of());

System.out.println(changed);     // false
System.out.println(destination); // [A, D]
~~~

Nguồn rỗng không cung cấp phần tử mới để chèn.

Giá trị boolean không phải:

- Số phần tử thêm.
- Chỉ số cuối của nhóm.
- Một List kết quả.
- Chỉ báo rằng các phần tử nguồn đều khác với mọi giá trị đã có ở đích.

Nếu chèn B, B vào ArrayList, đích vẫn tăng hai phần tử và kết quả là true. List không loại trùng như Set.

### Nguồn rỗng không bỏ qua mọi điều kiện

Không coi nguồn rỗng là lý do truyền vị trí tùy ý hoặc bỏ qua chính sách khả năng sửa của nguồn.

Ví dụ, với một ArrayList có size `2`, index `3` vẫn ngoài miền chèn. Một danh sách không hỗ trợ addAll còn có thể từ chối lời gọi dù nó không tạo thêm phần tử nào.

Cũng không suy từ false rằng mọi trạng thái nội bộ hoặc iterator cũ chắc chắn không bị ảnh hưởng. Boolean nói về kết quả thay đổi nội dung theo hợp đồng; đừng dùng nó như một giao thức quản lý phiên bản iterator.

### Collection null khác collection rỗng

~~~java
destination.addAll(1, null); // NullPointerException
~~~

`null` không phải một collection không có phần tử.

Một nguồn có chứa phần tử `null` lại là trường hợp khác. ArrayList cho phép phần tử null, nên nguồn như `Arrays.asList("B", null)` có thể được chèn vào nó. Với đích cấm null, phải theo hợp đồng và kiểm tra dữ liệu tương ứng.

Không dùng `List.of("B", null)` để tạo nguồn cho ca này, vì chính List.of từ chối null trước khi tới lời gọi addAll.

## 6. Vì sao vòng lặp add tại cùng một chỉ số bị đảo thứ tự?

Cách viết:

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));

for (String value : List.of("B", "C")) {
    destination.add(1, value);
}

System.out.println(destination); // [A, C, B, D]
~~~

Diễn biến:

~~~text
Ban đầu:       [A, D]
add(1, "B"):   [A, B, D]
add(1, "C"):   [A, C, B, D]
~~~

Lần thứ hai vẫn chèn vào vị trí `1`, trước B vừa thêm. Vì vậy cách này không tương đương addAll(1, [B, C]).

Nếu phải viết vòng lặp theo ý định giữ thứ tự, cần cập nhật điểm chèn:

~~~java
int insertion = 1;
for (String value : List.of("B", "C")) {
    destination.add(insertion, value);
    insertion++;
}
~~~

Đoạn này giả định bắt đầu từ đích ban đầu A, D. Kết quả là A, B, C, D.

Tuy nhiên, khi nguồn đã là Collection và mục tiêu là chèn nguyên nhóm, một lời gọi addAll thường biểu đạt ý định trực tiếp hơn. Với một số triển khai, nó còn có thể giảm việc dịch phần đuôi lặp lại.

Không lấy khả năng đúng của vòng lặp với một ArrayList nhỏ để kết luận hai phương án có cùng chi phí trên mọi List.

## 7. Nguồn độc lập không bị tiêu thụ hoặc gắn thành view

Ví dụ:

~~~java
List<String> destination = new ArrayList<>(List.of("A", "D"));
List<String> source = new ArrayList<>(List.of("B", "C"));

destination.addAll(1, source);

System.out.println(source); // [B, C]

source.set(0, "source-only");

System.out.println(source);      // [source-only, C]
System.out.println(destination); // [A, B, C, D]
~~~

Đích không giữ một liên kết động kiểu “đoạn này luôn nhìn theo các ô của source”. Nó đã thêm các phần tử được cung cấp trong lần thao tác đó.

Thay phần tử mà source giữ sau khi chèn không tự thay phần tử tương ứng trong destination. Xóa các phần tử khỏi source cũng không phải cách xóa nhóm đã được chèn khỏi đích.

### Nhưng không có sao chép sâu đối tượng

Các phần tử dạng đối tượng được thêm bằng tham chiếu. Nếu cả nguồn và đích cùng giữ tham chiếu tới một đối tượng có thể thay đổi, việc sửa nội dung đối tượng đó có thể ảnh hưởng điều cả hai bên quan sát.

Phân biệt:

- Thay một ô của source bằng `source.set(...)`: thay tham chiếu ở source.
- Sửa nội dung đối tượng mà cả hai bên cùng giữ: cùng một đối tượng được dùng chung.
- Sao chép sâu: cần chính sách sao chép riêng của ứng dụng, addAll không tự làm.

Các ví dụ String dùng đối tượng bất biến để quan sát thứ tự và tính độc lập về cấu trúc danh sách, không chứng minh mọi kiểu phần tử đều bất biến.

## 8. Nguồn và đích dùng chung dữ liệu: cần chụp nhóm trước

Không viết một thuật toán tổng quát dựa vào hành vi tự chèn chính danh sách:

~~~java
// Không dựa vào lời gọi này như một hợp đồng sao chép tổng quát.
destination.addAll(position, destination);
~~~

Hợp đồng không xác định hành vi chung nếu collection nguồn bị sửa trong khi thao tác đang thực hiện. Trường hợp nguồn chính là đích không rỗng là một tình huống phải tránh dựa vào hành vi cụ thể. Việc một triển khai có thể tạm chụp nguồn và cho kết quả dễ hiểu trong một lần chạy không biến nó thành bảo đảm chung.

Tương tự, một `subList` có thể là view của chính đích. Sửa đích có thể ảnh hưởng cấu trúc mà view nguồn dựa vào.

### Chụp phần cần chèn trước khi sửa đích

~~~java
List<String> destination =
        new ArrayList<>(List.of("A", "B", "C", "D"));

List<String> captured =
        new ArrayList<>(destination.subList(0, 2));

destination.addAll(2, captured);

System.out.println(destination); // [A, B, A, B, C, D]
~~~

Nhóm A, B được chụp vào một collection có cấu trúc riêng trước khi destination bị thay đổi.

Trong chương trình này không có thay đổi đồng thời của nguồn khi chụp. Một lời gọi tạo bản sao không tự giải quyết việc luồng khác đang sửa dữ liệu; nếu có chia sẻ nhiều luồng, cần một quy trình đồng bộ hoặc ảnh chụp phù hợp.

Sau khi cấu trúc gốc bị đổi, cũng không tiếp tục dùng một view cũ theo giả định mọi vị trí vẫn hợp lệ. Bài dùng `captured` độc lập nên không cần truy cập lại view đã dùng để tạo nhóm.

## 9. Kiểu generic: Collection<? extends E>

Nếu đích là `List<Number>`, có thể nhận một nguồn `List<Integer>`:

~~~java
List<Number> destination =
        new ArrayList<>(List.of(0.5, 1.5));

List<Integer> integers = List.of(10, 20);
destination.addAll(1, integers);

System.out.println(destination); // [0.5, 10, 20, 1.5]
~~~

Đích nhận các phần tử Integer vì mỗi Integer là một Number.

`? extends E` ở tham số nguồn giúp đọc các phần tử có kiểu phù hợp để thêm vào đích. Nó không có nghĩa phương thức biến nguồn thành `List<Number>`, và không cần ép kiểu toàn bộ collection để làm điều đó.

Ngược lại, một `List<Object>` không được tự coi là nguồn hợp lệ cho `List<String>` chỉ vì người gọi tin các phần tử hiện tại đều là String. Kiểm tra kiểu tĩnh xét hợp đồng có thể chứa phần tử gì, không chỉ một ảnh dữ liệu đang quan sát.

### add không phải addAll

Với `List<String>`, gọi `add(sourceList)` không phải cách thêm các String của sourceList; kiểu phần tử String không khớp một đối tượng List.

Với một đích đủ rộng như `List<Object>`, `add(sourceList)` có thể thêm **một đối tượng List** làm một phần tử. `addAll(sourceList)` lại thêm từng phần tử trực tiếp của collection nguồn.

addAll cũng không tự làm phẳng mọi mức lồng nhau. Nó xử lý các phần tử trực tiếp do source cung cấp; nếu những phần tử đó là các List con phù hợp với kiểu đích, chúng vẫn là các phần tử dạng List con.

## 10. Khả năng chỉnh sửa và ngoại lệ

| Vấn đề | Điều cần kiểm tra |
| --- | --- |
| Vị trí chèn | Phải từ 0 đến size của đích ở thời điểm thao tác. |
| Khả năng hỗ trợ | Đích phải hỗ trợ thao tác làm tăng kích thước. |
| Nguồn | Không được là tham chiếu null. |
| Kiểu và giá trị phần tử | Đáp ứng quy tắc của đích, gồm chính sách null nếu có. |
| Nguồn bị sửa trong khi thao tác | Phải tránh hoặc tuân theo một chính sách concurrent được công bố rõ. |

ArrayList và LinkedList có thể sửa thông thường hỗ trợ indexed addAll. Một danh sách kích thước cố định từ Arrays.asList không hỗ trợ chèn thêm; danh sách không cho sửa từ List.of hoặc List.copyOf cũng không hỗ trợ.

Chỉ số hợp lệ không làm một thao tác không hỗ trợ trở thành hợp lệ:

~~~java
List<String> fixed = Arrays.asList("A", "D");

// Vị trí 1 hợp lệ, nhưng danh sách không cho tăng kích thước.
fixed.addAll(1, List.of("B", "C")); // UnsupportedOperationException
~~~

Không cần dự đoán thứ tự ngoại lệ khi cùng lúc vi phạm nhiều điều kiện. Tách ca kiểm tra chỉ số, nguồn null và đích không hỗ trợ để biết đang kiểm chứng điều gì.

### Một lời gọi không có nghĩa một giao dịch

Không có một bảo đảm chung rằng addAll trên mọi List sẽ kiểm tra toàn bộ rồi hoặc thêm đủ tất cả hoặc không thay đổi gì khi gặp lỗi.

Một triển khai, collection chuyên biệt hoặc nguồn tùy biến có thể có cơ chế và hành vi lỗi khác. Không bắt một ngoại lệ giữa chừng rồi mặc nhiên kết luận đích chưa hề bị sửa.

Nếu yêu cầu là giữ nguyên dữ liệu gốc khi chuẩn bị kết quả không thành công, có thể xây một danh sách kết quả riêng, kiểm tra rồi chỉ dùng kết quả khi bước chuẩn bị hoàn tất.

Điều này không tự tạo giao dịch nhiều luồng hoặc nhiều tài nguyên; phạm vi bảo đảm phải được thiết kế đúng với yêu cầu.

## 11. Tạo danh sách kết quả mà không sửa nguồn gốc

Một hàm tiện ích có thể biểu đạt rõ lựa chọn tạo kết quả mới:

~~~java
// Đặt phương thức trong một lớp; cần import List, Collection và ArrayList.
static <T> List<T> withInserted(
        List<? extends T> original,
        int index,
        Collection<? extends T> incoming
) {
    List<T> result = new ArrayList<>(original);
    List<T> batch = new ArrayList<>(incoming);
    result.addAll(index, batch);
    return result;
}
~~~

Ví dụ:

~~~java
List<String> original = List.of("A", "D");
List<String> result = withInserted(original, 1, List.of("B", "C"));

System.out.println(result);   // [A, B, C, D]
System.out.println(original); // [A, D]
~~~

Hàm chọn rõ:

- Kết quả là một ArrayList mới có thể sửa.
- Không thay cấu trúc original.
- Chụp incoming thành batch trước khi chèn vào result.
- Dùng đúng quy tắc vị trí chèn của result.

Đây không phải sao chép sâu. Hàm cũng không tự bảo toàn mọi giới hạn riêng của một lớp List chuyên biệt mà original có thể thuộc về, vì kết quả đã được chọn là ArrayList. Nếu ứng dụng cần các giới hạn đó, phải kiểm tra hoặc dùng một kiểu kết quả phù hợp.

Với dữ liệu được chia sẻ giữa nhiều luồng, việc đọc original và incoming để tạo bản sao vẫn cần tuân theo chính sách nhất quán của nguồn.

## 12. Chi phí: vì sao chèn theo nhóm có thể tốt hơn thêm lặp?

Gọi n là size đích, p là vị trí chèn, m là kích thước nhóm.

Ở triển khai ArrayList thông thường, một phép chèn theo nhóm có thể tạo chỗ cho m phần tử bằng cách dịch phần đuôi một lần, rồi đặt nhóm vào khoảng trống. Nếu cần mở rộng mảng nội bộ, còn có chi phí cấp phát và chuyển dữ liệu.

Mô hình chi phí thường gặp:

~~~text
Đọc/chuẩn bị m phần tử nguồn
+ dịch n - p phần tử đuôi
+ đặt m phần tử vào vùng chèn
+ chi phí mở rộng nếu cần
~~~

Trong khi đó, thêm từng phần tử vào giữa có thể phải dịch phần đuôi nhiều lần. Kết quả nội dung có thể giống nhau nếu chỉ số được cập nhật đúng, nhưng số lần di chuyển dữ liệu không nhất thiết giống.

Tham khảo các triển khai và khả năng của [ArrayList.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#addAll(int,java.util.Collection)) và [LinkedList.addAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html#addAll(int,java.util.Collection)).

Với LinkedList, cách thực hiện dựa trên tìm vị trí và tạo/nối các nút, không phải dịch mảng phần đuôi. Tuy nhiên, tìm vị trí theo chỉ số vẫn có chi phí.

Không coi interface List là một cam kết rằng mọi addAll đều có cùng thuật toán hoặc luôn nhanh hơn mọi vòng lặp. Xét triển khai, kích thước nhóm, vị trí chèn và chi phí nguồn. Với nguồn lớn, việc chụp một batch còn có nhu cầu bộ nhớ riêng.

## 13. Chương trình hoàn chỉnh

Lưu thành **IndexedAddAllDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;

public class IndexedAddAllDemo {
    public static void main(String[] args) {
        List<String> destination = new ArrayList<>(List.of("A", "D"));
        List<String> incoming = new ArrayList<>(List.of("B", "C"));

        boolean changed = destination.addAll(1, incoming);
        System.out.println("Changed = " + changed);
        System.out.println("Inserted = " + destination);
        System.out.println("Size = " + destination.size());
        System.out.println("Source after insertion = " + incoming);

        incoming.set(0, "source-only");
        System.out.println("Source after set = " + incoming);
        System.out.println("Destination after source set = " + destination);

        boolean emptyChanged = destination.addAll(2, List.of());
        System.out.println("Empty source changed = " + emptyChanged);
        System.out.println("After empty insertion = " + destination);

        destination.addAll(0, List.of("H1", "H2"));
        destination.addAll(destination.size(), List.of("T1", "T2"));
        System.out.println("Head and tail batches = " + destination);

        List<String> empty = new ArrayList<>();
        empty.addAll(0, List.of("first", "second"));
        System.out.println("Empty destination = " + empty);

        List<String> repeated = new ArrayList<>(List.of("A", "D"));
        for (String value : List.of("B", "C")) {
            repeated.add(1, value);
        }
        System.out.println("Repeated same-index add = " + repeated);

        LinkedHashSet<String> orderedSource =
                new LinkedHashSet<>(List.of("C", "B", "C"));
        List<String> fromSet = new ArrayList<>(List.of("A", "D"));
        fromSet.addAll(1, orderedSource);
        System.out.println("Ordered set source = " + fromSet);

        List<String> duplicates = new ArrayList<>(List.of("A", "D"));
        duplicates.addAll(1, List.of("B", "B"));
        System.out.println("Duplicate source elements = " + duplicates);

        List<String> original = List.of("A", "D");
        List<String> result = withInserted(original, 1, List.of("B", "C"));
        System.out.println("Copy result = " + result);
        System.out.println("Original unchanged = " + original);

        List<String> overlap =
                new ArrayList<>(List.of("A", "B", "C", "D"));
        List<String> captured = new ArrayList<>(overlap.subList(0, 2));
        overlap.addAll(2, captured);
        System.out.println("Captured overlapping range = " + overlap);

        List<Number> numbers = new ArrayList<>(List.of(0.5, 1.5));
        List<Integer> integers = List.of(10, 20);
        numbers.addAll(1, integers);
        System.out.println("Subtype source = " + numbers);

        List<String> validTarget = new ArrayList<>(List.of("A", "D"));
        expect("Negative index", IndexOutOfBoundsException.class,
                () -> validTarget.addAll(-1, List.of("B")));
        expect("Index beyond size", IndexOutOfBoundsException.class,
                () -> validTarget.addAll(3, List.of("B")));
        expect("Null source", NullPointerException.class,
                () -> validTarget.addAll(1, null));

        List<String> fixed = Arrays.asList("A", "D");
        expect("Fixed-size destination", UnsupportedOperationException.class,
                () -> fixed.addAll(1, List.of("B", "C")));
    }

    private static <T> List<T> withInserted(
            List<? extends T> original,
            int index,
            Collection<? extends T> incoming
    ) {
        List<T> result = new ArrayList<>(original);
        List<T> batch = new ArrayList<>(incoming);
        result.addAll(index, batch);
        return result;
    }

    private static void expect(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable operation
    ) {
        try {
            operation.run();
            throw new AssertionError("Expected " + expected.getSimpleName());
        } catch (RuntimeException exception) {
            if (!expected.isInstance(exception)) {
                throw exception;
            }
            System.out.println(label + " -> "
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 IndexedAddAllDemo.java
java IndexedAddAllDemo
~~~

Stdout:

~~~text
Changed = true
Inserted = [A, B, C, D]
Size = 4
Source after insertion = [B, C]
Source after set = [source-only, C]
Destination after source set = [A, B, C, D]
Empty source changed = false
After empty insertion = [A, B, C, D]
Head and tail batches = [H1, H2, A, B, C, D, T1, T2]
Empty destination = [first, second]
Repeated same-index add = [A, C, B, D]
Ordered set source = [A, C, B, D]
Duplicate source elements = [A, B, B, D]
Copy result = [A, B, C, D]
Original unchanged = [A, D]
Captured overlapping range = [A, B, A, B, C, D]
Subtype source = [0.5, 10, 20, 1.5]
Negative index -> IndexOutOfBoundsException
Index beyond size -> IndexOutOfBoundsException
Null source -> NullPointerException
Fixed-size destination -> UnsupportedOperationException
~~~

Hàm `expect` chỉ bắt loại lỗi đang được kiểm chứng. Nếu nhận một RuntimeException khác, nó ném lại để không ghi nhận sai là đã đạt ca thử; nếu không có lỗi như dự kiến, nó ném AssertionError.

Chương trình không thử hành vi không được xác định của tự addAll hoặc sửa nguồn trong khi addAll đang thực hiện. Với nguồn chồng lấn, nó chụp batch trước.

## 14. Giải thích kết quả

**Changed, Inserted và Size**

Chèn B, C tại vị trí `1` của A, D tạo A, B, C, D và size `4`. Boolean true nói đích đã có thay đổi, không phải đã thêm đúng một phần tử.

**Source after insertion**

Nguồn vẫn là B, C. addAll không di chuyển các phần tử ra khỏi collection nguồn.

**Source after set**

Thay ô đầu của nguồn bằng source-only không biến ô tương ứng của đích thành source-only. Đích không phải một view ghép động theo nguồn.

**Empty source**

Không có phần tử mới để chèn; ArrayList trả false và nội dung vẫn A, B, C, D. Chương trình không từ kết quả này suy ra điều gì về iterator cũ.

**Head and tail**

Nhóm H1, H2 được chèn trước phần đầu, còn T1, T2 thêm cuối. Thứ tự nội bộ của từng batch đều được giữ.

**Repeated same-index add**

Chèn B rồi C nhưng luôn tại chỉ số `1` tạo C trước B. Nó không tương đương addAll tại một vị trí với nguồn B, C.

**Ordered set source**

Nguồn LinkedHashSet chứa C rồi B, nên nhóm chèn có thứ tự C rồi B. Đích không tự sort.

**Duplicate source elements**

Hai B đều xuất hiện trong List đích. Không có cơ chế loại trùng tự động trong phép chèn vào ArrayList này.

**Copy result**

Hàm tiện ích tạo A, B, C, D nhưng original vẫn A, D, vì thao tác diễn ra trên result mới.

**Captured overlapping range**

A, B được chụp từ một đoạn của đích trước khi chèn. Kết quả A, B, A, B, C, D không dựa vào hành vi nguồn tự thay đổi trong lúc chèn.

**Subtype source**

Các Integer `10` và `20` được thêm vào List<Number> giữa hai Double. Wildcard của nguồn cho phép quan hệ kiểu này mà không ép kiểu collection.

**Các ca lỗi**

Chỉ số âm và chỉ số vượt size bị từ chối; nguồn null bị từ chối; đích kích thước cố định không thể chèn cả nhóm. Các ca được tạo riêng để xác định đúng điều kiện đang kiểm tra.

## 15. Kiểm thử và lỗi thường gặp

Kiểm tra một phép chèn theo nhóm bằng ba phần:

1. Prefix trước vị trí chèn giữ nguyên.
2. Batch xuất hiện đúng thứ tự và đủ số lần phần tử.
3. Suffix cũ giữ thứ tự, bắt đầu sau batch.

Ngoài ra, kiểm tra size mới, giá trị boolean và việc có chủ ý sửa nguồn gốc hay tạo kết quả mới.

Các ca quan trọng:

- Đích rỗng và nguồn không rỗng.
- Nguồn rỗng tại một vị trí hợp lệ.
- Chèn đầu, giữa và cuối.
- Nguồn có một phần tử, nhiều phần tử, phần tử trùng.
- Nguồn có thứ tự khác thứ tự tự nhiên.
- Chỉ số `-1`, `size()` và `size() + 1`.
- Nguồn null so với nguồn chứa null.
- Đích cố định kích thước hoặc không cho sửa.
- Nguồn chồng lấn được chụp riêng trước khi dùng.
- Nguồn dùng kiểu con của kiểu phần tử đích.

| Hiểu nhầm | Cách hiểu cần giữ |
| --- | --- |
| addAll ghi đè các phần tử ở vị trí chèn | Nó tạo chỗ và đẩy phần đuôi sang phải. |
| addAll trả số lượng đã thêm | Nó trả boolean về thay đổi của đích. |
| Nguồn phải là List | Collection phù hợp có thể được dùng; thứ tự theo nguồn. |
| Đích là ArrayList nên nhóm luôn được sort | Không có thao tác sắp xếp tự động. |
| Chèn lặp tại cùng chỉ số giữ nguyên thứ tự nguồn | Mỗi lần mới chen trước phần tử ở vị trí đó, có thể đảo thứ tự nhóm. |
| Nguồn rỗng là null | Hai trạng thái hoàn toàn khác. |
| Nguồn bị tiêu thụ hoặc gắn động vào đích | Với các nguồn độc lập, cấu trúc nguồn còn nguyên và đích không thành view theo ô của nguồn. |
| addAll sao chép sâu mọi đối tượng | Các phần tử dạng đối tượng vẫn có thể dùng chung tham chiếu. |
| Tự chèn hoặc dùng view chồng lấn luôn có bảo đảm | Cần tránh dựa vào nguồn bị sửa trong quá trình thực hiện; chụp batch trước khi phù hợp. |
| Một lời gọi đồng nghĩa hoặc đủ tất cả hoặc không đổi gì khi lỗi | Không có bảo đảm giao dịch chung cho mọi List và nguồn. |

## 16. Thực hành

1. Từ `[A, F]`, chèn `[B, C, D, E]` tại vị trí thích hợp. Viết chỉ số trước và sau của F.
2. Dự đoán kết quả khi nguồn là `[C, B]` và khi nguồn là một LinkedHashSet tạo từ `[C, B, C]`.
3. Viết vòng lặp add từng phần tử tương đương về nội dung với addAll, sau đó chỉ ra lỗi khi không tăng vị trí chèn.
4. Tạo một hàm chèn batch nhưng giữ nguyên original. Kiểm tra cả kết quả, original và việc phần tử dạng đối tượng có thể vẫn dùng chung.
5. Chụp một đoạn đầu của danh sách rồi chèn bản chụp vào giữa chính danh sách đó. Giải thích vì sao chụp trước quan trọng.
6. Kiểm thử nguồn rỗng, nguồn null, chèn ở size và chèn ở size + 1 trên một ArrayList có thể sửa.
7. Với một bài toán nhập dữ liệu, xác định thứ tự batch đến từ đâu, nguồn có thể bị đổi khi đọc không, và cần kiểm tra gì trước khi dùng kết quả.

Một phép chèn theo nhóm gồm đích, vị trí và thứ tự nguồn. Khi ba yếu tố này rõ ràng, có thể suy ra toàn bộ kết quả bằng mô hình phần đầu – batch – phần đuôi, rồi xem xét riêng khả năng sửa, nguồn dùng chung và chi phí triển khai.
