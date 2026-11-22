# Hợp đồng API so với chi tiết cài đặt có thể đổi giữa các JDK

Khi học collection, ta thường vừa đọc Javadoc vừa xem mã nguồn JDK. Hai nguồn này trả lời hai câu hỏi liên quan nhưng khác nhau:

- **Hợp đồng API:** chương trình được phép yêu cầu gì và có thể dựa vào điều gì?
- **Chi tiết cài đặt:** một phiên bản thư viện cụ thể đang thực hiện yêu cầu đó bằng cách nào?

Phân biệt được hai lớp thông tin giúp viết chương trình vẫn đúng khi đổi cách triển khai, nâng cấp JDK hoặc đổi nhà cung cấp bản phân phối. Nó cũng giúp đọc mã nguồn sâu mà không biến một quan sát hiện tại thành quy tắc vĩnh viễn của Java.

Ví dụ, `ArrayList` bảo đảm truy cập theo chỉ số và mô tả một số đặc tính hiệu năng. Nhưng tỷ lệ tăng mảng chính xác không phải điều ứng dụng được quyền cố định. `HashMap` lưu ánh xạ theo khóa, nhưng không bảo đảm thứ tự duyệt mà ta tình cờ quan sát khi in nó.

Bài này sử dụng Java 17 làm mốc API cho ví dụ. Khi nhắc đến khác biệt phiên bản, cần xác định đó là thay đổi có tài liệu hay chỉ là khả năng mà hợp đồng để mở.

## 1. Hợp đồng API gồm nhiều hơn tên phương thức

Một chữ ký như `boolean add(E e)` mới chỉ cho biết cách gọi và kiểu kết quả. Để dùng đúng, còn cần biết:

| Thành phần hợp đồng | Câu hỏi cần đọc |
| --- | --- |
| Ý nghĩa thao tác | Thêm vào đâu, tìm theo quy tắc nào, thay dữ liệu hay tạo kết quả mới? |
| Điều kiện đầu vào | Có chấp nhận `null`, chỉ số biên hoặc kiểu phần tử này không? |
| Giá trị trả về | Là phần tử, giá trị cũ, số lượng hay chỉ báo có thay đổi? |
| Ngoại lệ | Khi nào đầu vào bị từ chối hoặc thao tác không được hỗ trợ? |
| Thứ tự | Giữ thứ tự chèn, thứ tự chỉ số, thứ tự comparator hay không cam kết? |
| Khả năng sửa | Có được thêm, xóa, thay phần tử không? |
| Quan hệ với dữ liệu khác | Là bản sao hay view gắn với nguồn? |
| Đồng thời | Có bảo đảm an toàn, nguyên tử hoặc cách quan sát thay đổi không? |
| Hiệu năng được công bố | Có bảo đảm độ phức tạp và giả định đi kèm không? |

Không phải mọi API đều có cùng mức cam kết ở từng mục. Nếu tài liệu không hứa một thuộc tính, chương trình không nên tự nâng quan sát thành lời hứa.

Chẳng hạn, hai lần chạy có thể cùng cho một thứ tự `HashMap`; điều đó chỉ chứng minh hai lần chạy ấy cho cùng thứ tự. Nó không tạo ra hợp đồng “map luôn sắp theo khóa”.

## 2. Đọc đúng tầng hợp đồng

### 2.1. Interface quy định mô hình chung

`List`, `Set`, `Queue` và `Map` diễn đạt những mô hình khác nhau. Một phương thức nhận `List<Integer>` có thể duyệt theo thứ tự danh sách mà không cần biết phần tử được lưu trong mảng hay các nút liên kết.

Nhưng `List` có các thao tác sửa tùy chọn. Chỉ vì kiểu khai báo có phương thức `add` không có nghĩa mọi đối tượng `List` nhận vào đều hỗ trợ `add`.

```java
List<String> first = new ArrayList<>();
List<String> second = List.of("A");
```

Cả hai biến có kiểu `List<String>`, nhưng không có cùng quyền sửa. Nếu một phương thức cần thay đổi danh sách nhận vào, hợp đồng của chính phương thức ấy phải nói rõ yêu cầu hoặc tự tạo một bản có thể sửa.

Interface cũng không quy định mọi chi phí truy cập giống nhau. Một vòng lặp dùng `get(i)` nhiều lần có thể hoạt động khác về thời gian trên `ArrayList` và `LinkedList`. [Java 17: List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

### 2.2. Lớp cụ thể có thể đưa ra bảo đảm mạnh hơn

Khi chủ động chọn `ArrayList`, ta được dựa vào các thuộc tính đã công bố của chính lớp đó, chẳng hạn hỗ trợ các thao tác sửa thông thường và một số đặc điểm hiệu năng.

Điều này không mâu thuẫn với lời khuyên khai báo theo interface:

```java
List<String> names = new ArrayList<>();
```

Biến vẫn giữ đối tượng `ArrayList`; cách khai báo không xóa đặc điểm của đối tượng. Tuy nhiên, khi truyền biến qua một ranh giới API chỉ nói “nhận `List`”, bên nhận không nên giả định mọi lời gọi trong tương lai đều truyền `ArrayList`.

Nếu thật sự cần một khả năng đặc thù như `ensureCapacity`, có thể chọn kiểu cụ thể ở phần mã sở hữu dữ liệu. Đó là phụ thuộc có chủ đích vào API công khai, khác với đọc trường riêng bằng reflection.

### 2.3. Phương thức tạo có hợp đồng riêng

Một phương thức trả `List<T>` không tự hứa lớp cụ thể hoặc quyền sửa của kết quả. Phải đọc hợp đồng của chính phương thức tạo:

| Cách tạo | Điều có thể dựa vào |
| --- | --- |
| `new ArrayList<>(source)` | Tạo đối tượng `ArrayList` chứa các phần tử nguồn theo thứ tự duyệt nguồn |
| `Arrays.asList(array)` | Danh sách kích thước cố định, gắn với mảng được truyền vào |
| `List.of(...)` | Danh sách không sửa được, có các hạn chế đầu vào đã công bố |
| `List.copyOf(source)` | Danh sách không sửa được, không phản ánh việc thêm/xóa sau đó của nguồn |
| `Collections.unmodifiableList(source)` | View không cho sửa qua chính nó, vẫn gắn với nguồn |

Không gom tất cả thành “một danh sách immutable”. View có thể thay đổi nội dung quan sát được nếu nguồn bị sửa; một danh sách không sửa cấu trúc cũng không tự đóng băng các đối tượng phần tử. [Java 17: Arrays.asList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)), [Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))

## 3. Cách đọc Javadoc có hệ thống

Khi mở tài liệu một lớp hoặc phương thức, nên đọc theo thứ tự:

1. Xác nhận đúng phiên bản Java.
2. Đọc mô tả lớp/interface trước, vì quy tắc chung có thể không lặp ở từng phương thức.
3. Đọc mô tả phương thức, tham số và giá trị trả về.
4. Đọc ngoại lệ, điều kiện tùy chọn và ghi chú `null`.
5. Theo các liên kết đến phương thức kế thừa hoặc đặc tả liên quan.
6. Phân biệt giải thích cách dùng với mô tả triển khai.
7. Đọc `Since` nếu cần hỗ trợ một mức Java tối thiểu.

Tài liệu được sinh từ Javadoc có các phần tham số, trả về, ngoại lệ và lịch sử phiên bản. Đừng chỉ đọc tên phương thức hoặc một ví dụ rồi bỏ qua điều kiện áp dụng. [Đặc tả comment Javadoc của JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html)

### Các phần ghi chú có ý nghĩa khác nhau

Trong tài liệu JDK, có thể gặp các phần:

- **API Note:** giải thích cho người sử dụng, nêu tình huống hoặc cách dùng.
- **Implementation Requirements:** mô tả yêu cầu/cách thực hiện gắn với phần triển khai được tài liệu hóa, chẳng hạn một phương thức mặc định.
- **Implementation Note:** giải thích lựa chọn hoặc đặc điểm triển khai.

Không đọc mọi đoạn như thể nó ràng buộc mọi lớp triển khai interface. Ví dụ, `Collection.removeIf` mô tả thuật toán mặc định dựa trên iterator. Một lớp ghi đè `removeIf` không vì thế phải dùng đúng cùng cấu trúc vòng lặp.

Ngược lại, cũng không bỏ qua một bảo đảm chỉ vì nó nói về hiệu năng hoặc cấu trúc. Nếu tài liệu công khai của lớp đã nêu một đặc tính với phạm vi cụ thể, đó là thông tin để lựa chọn lớp trong phạm vi ấy. [Java 17: Collection.removeIf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate))

## 4. ArrayList: bảo đảm công khai và điều để mở

Tài liệu Java 17 mô tả `ArrayList` là cách triển khai danh sách bằng mảng có thể thay đổi dung lượng. Một số thao tác như `get`, `set` và `size` có thời gian hằng số; thêm phần tử có chi phí hằng số khấu hao.

Tài liệu đồng thời nói chi tiết chính sách tăng dung lượng không được quy định, ngoài bảo đảm chi phí khấu hao.

| Phát biểu | Đánh giá |
| --- | --- |
| `get(i)` trả phần tử ở chỉ số hợp lệ `i` | Có thể dựa vào |
| Thêm cuối giữ thứ tự danh sách | Có thể dựa vào |
| Dung lượng đủ chứa số phần tử hiện có | Thuộc mô hình được công bố |
| Mỗi lần đầy, mảng phải tăng đúng một tỷ lệ cố định | Không phải cam kết của API |
| Mảng thật luôn được cấp phát ngay tại đúng thời điểm quan sát được | Không nên suy từ API nếu không có bảo đảm tương ứng |
| `size()` bằng số ô đã dành trước | Sai ý nghĩa API |

Ví dụ:

```java
ArrayList<String> values = new ArrayList<>(100);
System.out.println(values.size()); // 0
```

Tham số dung lượng không tạo 100 phần tử. Nếu cần tối ưu dựa trên số phần tử dự kiến, dùng constructor hoặc `ensureCapacity`; không phải lấy công thức tăng mảng trong mã nguồn để suy ra dữ liệu nghiệp vụ.

Có thể học công thức đang được một bản OpenJDK sử dụng để hiểu chi phí sao chép. Khi ghi chú, hãy gắn nó với bản nguồn cụ thể và giữ nó ở vai trò giải thích, không phải điều kiện để chương trình trả kết quả đúng. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

## 5. HashMap: không biến thứ tự quan sát thành quy tắc

`HashMap` công khai rằng không bảo đảm thứ tự các ánh xạ. Thứ tự tình cờ trông giống thứ tự số, thứ tự thêm hoặc một thứ tự ổn định vẫn không phải một yêu cầu đối với lần chạy khác.

Đoạn kiểm thử sau phụ thuộc sai:

```java
// Ví dụ sai về kỳ vọng, không phải bảo đảm của HashMap.
assert map.keySet().toString().equals("[A, B, C]");
```

Nếu yêu cầu chỉ là các ánh xạ đúng, kiểm tra bằng bình đẳng của map hoặc từng ánh xạ. Nếu sản phẩm cần một báo cáo sắp theo khóa, tạo một phép chiếu có thứ tự rõ ràng:

```java
Map<String, Integer> sorted = new TreeMap<>(map);
System.out.println(sorted);
```

Nếu cần giữ thứ tự chèn, xem xét `LinkedHashMap` theo hợp đồng của nó. Mỗi lựa chọn diễn đạt một yêu cầu khác nhau; không dùng một `HashMap` rồi hy vọng một tập khóa cụ thể sẽ cho thứ tự mong muốn. [Java 17: HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html)

### Một thay đổi lịch sử đã được ghi nhận

Tài liệu cải tiến Collections của Java SE 8 mô tả việc dùng cây cân bằng ở các vùng băm có nhiều khóa va chạm, nhằm cải thiện hiệu năng. Tài liệu cũng cảnh báo việc này có thể làm thay đổi thứ tự duyệt của `HashMap`/`HashSet` trong một số tình huống.

Đây là minh chứng cụ thể cho việc một thay đổi bên trong vẫn có thể phù hợp API nhưng làm lộ lỗi của chương trình đã phụ thuộc vào điều không được bảo đảm. Nó không có nghĩa mọi lần nâng JDK đều thay thứ tự, và cũng không có nghĩa mọi vùng băm luôn là cây. [Oracle: cải tiến Collections trong Java SE 8](https://docs.oracle.com/javase/8/docs/technotes/guides/collections/changes8.html)

Các ngưỡng chuyển cấu trúc, phép trộn bit và hình dạng trường nội bộ hữu ích khi nghiên cứu một bản nguồn. Không dùng chúng để nhận biết loại dữ liệu hoặc quyết định quyền truy cập, nghiệp vụ hay tính duy nhất của khóa.

## 6. Không suy lớp cụ thể từ kiểu List trả về

Một lỗi phổ biến là quan sát lớp lúc chạy rồi ép kiểu theo quan sát đó:

```java
List<String> result = Stream.of("A", "B")
        .collect(Collectors.toList());

// Không được hợp đồng Collectors.toList bảo đảm:
ArrayList<String> assumed = (ArrayList<String>) result;
```

`Collectors.toList()` không bảo đảm kiểu triển khai, khả năng sửa, khả năng tuần tự hóa hoặc an toàn đồng thời của danh sách kết quả. Một bản JDK đang trả lớp nào không biến lớp ấy thành kiểu được hứa.

Nếu cần một `ArrayList` có thể sửa, yêu cầu nó trực tiếp:

```java
ArrayList<String> editable = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));

editable.add("C");
```

Nếu đã có một `List` và chỉ cần một bản có thể sửa, `new ArrayList<>(result)` cũng diễn đạt rõ ý định. [Java 17: Collectors.toList và toCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList())

### Stream.toList là một hợp đồng khác

`stream.toList()` trong Java 17 trả danh sách không sửa được. Việc viết ngắn hơn không làm nó đồng nghĩa với `collect(Collectors.toList())`.

```java
List<String> fixed = Stream.of("A", "B").toList();
fixed.add("C"); // UnsupportedOperationException
```

Dù tên gọi đều có “toList”, phải đọc từng phương thức. Đồng thời không dựa vào tên lớp nội bộ, khả năng tuần tự hóa hoặc nhận dạng tham chiếu của kết quả nếu tài liệu không bảo đảm. [Java 17: Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList())

## 7. Đối tượng không sửa được: nội dung và nhận dạng khác nhau

Với các factory như `List.of`, điều cần dùng thường là nội dung và hợp đồng không sửa được. Tên lớp nội bộ, việc hai lần gọi có dùng lại một đối tượng hay không, hoặc cách chia lớp theo số phần tử không phải yêu cầu mà người gọi nên đặt.

Ví dụ nên kiểm tra:

```java
List<String> actual = List.of("A", "B");
boolean sameContent = actual.equals(List.of("A", "B"));
```

Không dùng `actual == anotherList` để kiểm tra nội dung. Các đối tượng được tài liệu mô tả là value-based cũng không phù hợp để làm khóa đồng bộ dựa trên nhận dạng.

`List.copyOf(source)` không hứa luôn cấp phát một đối tượng mới. Nếu nguồn đã phù hợp, cách triển khai có thể tránh sao chép không cần thiết. Điều được yêu cầu là kết quả đáp ứng hợp đồng, bao gồm không phản ánh các thay đổi cấu trúc sau đó của nguồn, chứ không phải `result != source` phải luôn đúng. [Java 17: các factory và copyOf của List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

Cũng đừng suy từ “không phản ánh thêm/xóa ở nguồn” thành bản sao sâu. Nếu phần tử là đối tượng có thể sửa, các danh sách vẫn có thể tham chiếu cùng đối tượng phần tử.

## 8. Một ví dụ về thuật toán có thể đổi nhưng kết quả phải giữ

Tài liệu `Arrays` giải thích các mô tả thuật toán trong lớp được xem là ghi chú triển khai; có thể thay thuật toán nếu vẫn tuân thủ đặc tả. Ví dụ, sắp xếp mảng đối tượng phải giữ tính ổn định khi API quy định điều đó, nhưng không nhất thiết phải dùng một thuật toán cụ thể.

Phân biệt hai yêu cầu:

- “Các phần tử bằng nhau theo comparator giữ thứ tự tương đối ban đầu” là một tính chất kết quả có thể được bảo đảm.
- “Phương thức phải chia mảng theo đúng các đoạn có kích thước này” là một lựa chọn thuật toán, trừ khi hợp đồng nói rõ.

Đối với collection, cùng cách đọc ấy giúp tránh nhầm thuật toán sắp, cách dồn mảng hoặc cách tìm phần tử với điều mà bên gọi được bảo đảm. [Java 17: ghi chú triển khai của Arrays](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html)

“Chi tiết cài đặt có thể thay đổi” không có nghĩa thư viện được tự do bỏ tính ổn định hoặc đổi ý nghĩa giá trị trả về đã công bố. Chính ranh giới hợp đồng xác định phần nào được phép tối ưu.

## 9. Ngoại lệ và đồng thời cũng phải đọc đúng phạm vi

### 9.1. Fail-fast không phải cơ chế đồng bộ

Iterator của nhiều collection thông thường được mô tả là fail-fast. Nhưng việc ném `ConcurrentModificationException` là phát hiện theo khả năng, không phải bảo đảm phát hiện mọi sửa đổi không đồng bộ.

Chương trình không được dựa vào lập luận:

```java
// Lập luận sai:
// Nếu iterator không ném lỗi, dữ liệu chắc chắn đã được truy cập an toàn.
```

Nếu một bản JDK thay thời điểm kiểm tra hoặc tối ưu vòng duyệt, chương trình đã vi phạm quy tắc chia sẻ dữ liệu không trở thành đúng chỉ nhờ từng chạy qua. Hãy thiết kế quyền sở hữu dữ liệu, khóa hoặc cấu trúc đồng thời theo yêu cầu. [Java 17: ArrayList, giới hạn fail-fast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

### 9.2. Một ngoại lệ không hứa thời điểm hoặc thông điệp tùy ý

Khi API nêu một loại ngoại lệ, vẫn cần đọc điều kiện phát sinh. Đừng suy thêm rằng:

- Mọi đối tượng không hợp lệ đều bị từ chối ở cùng một bước.
- Thông điệp ngoại lệ luôn có cùng văn bản.
- Khi một thao tác lỗi, mọi thay đổi trước đó chắc chắn được hoàn tác.
- Một collection không cho sửa phải luôn chấp nhận thao tác không tạo thay đổi.

Với đầu vào không được hỗ trợ, tài liệu `Collection` còn cho phép một số truy vấn ném ngoại lệ hoặc cho kết quả theo các điều kiện tùy chọn. Những trường hợp này cần được đọc tại API cụ thể, không đoán từ một phiên bản đang dùng. [Java 17: Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)

Khi viết kiểm thử, chỉ so chuỗi thông báo lỗi nếu chính ứng dụng hoặc một hợp đồng cần kiểm chứng đã cam kết chuỗi ấy. Đối với JDK, thường nên kiểm tra loại ngoại lệ và trạng thái được đặc tả.

## 10. Đọc mã nguồn để hiểu, không để tự mở rộng lời hứa

Đọc nguồn JDK rất có giá trị khi muốn biết:

- Vì sao một thao tác tốn thời gian hoặc cấp phát nhiều bộ nhớ.
- Vòng lặp và cấu trúc dữ liệu hiện tại hoạt động thế nào.
- Một tối ưu hóa đã được thêm vào phiên bản nào.
- Lỗi cụ thể có liên quan đến thay đổi triển khai hay không.

Quy trình nên giữ hai ghi chú riêng:

| Ghi chú | Ví dụ cách viết |
| --- | --- |
| Điều ứng dụng được dựa vào | “Báo cáo cần sắp theo khóa; dùng một cấu trúc có thứ tự khóa.” |
| Quan sát triển khai | “Trong bản nguồn đang phân tích, thao tác này đi qua các nút của cấu trúc nội bộ theo cách sau...” |

Với quan sát triển khai, ghi rõ nhà cung cấp/bản phân phối, phiên bản đầy đủ, tag hoặc commit nguồn và điều kiện thử. Không lấy nhánh `master` hiện tại để giải thích chắc chắn cho một chương trình chạy trên JDK cũ mà chưa đối chiếu.

Việc một trường là `private`, tên lớp ở gói nội bộ hay một hằng số xuất hiện trong nguồn không khiến nó trở thành API được hỗ trợ. Truy cập bằng reflection hoặc cấu hình mở module cũng không tự tạo cam kết tương thích cho trường đó.

Không cần loại bỏ mọi kiến thức về triển khai khỏi bài học. Cần chỉ rõ vai trò của nó: cơ chế giải thích, dữ liệu chẩn đoán hoặc kết quả đo; không trình bày như quy tắc bắt buộc cho mọi JDK.

## 11. Kiểm thử theo hợp đồng thay vì theo tình cờ

### Những điều nên kiểm tra

- Nội dung danh sách và thứ tự mà hợp đồng danh sách yêu cầu.
- Tập khóa/giá trị hoặc các ánh xạ đúng của map.
- Khả năng sửa khi phương thức của chính ứng dụng cam kết kết quả có thể sửa.
- Hành vi view hoặc bản sao theo nguồn tạo đã chọn.
- Các điều kiện biên và loại ngoại lệ được đặc tả.
- Bất biến nghiệp vụ trước và sau thao tác.

### Những kỳ vọng cần loại bỏ nếu không có cam kết riêng

- Tên lớp nội bộ của kết quả factory.
- Thứ tự `HashMap` hoặc `HashSet`.
- Dung lượng riêng, số lần tăng mảng hoặc ngưỡng chuyển cây.
- Số lần gọi hàm phụ nếu API không cam kết.
- Thời gian chính xác tính bằng mili giây trên mọi máy.
- Việc một thao tác không đồng bộ “chắc chắn sẽ ném lỗi”.

Nếu yêu cầu sản phẩm cần một điều mà API hiện tại không hứa, hãy thay thiết kế: chọn kiểu có hợp đồng phù hợp, tạo bản sao rõ ràng hoặc đặt một lớp API do ứng dụng sở hữu với bảo đảm đã được thực hiện và kiểm thử.

Không nên sửa kiểm thử bằng cách chấp nhận mọi kết quả. Phải xác định điều nào là yêu cầu thực và biến nó thành một bảo đảm rõ trong thiết kế.

## 12. Nâng JDK: phân biệt khả dụng API với hành vi triển khai

Một API mới chỉ có ở phiên bản cao hơn là vấn đề khác với thay đổi thuật toán bên trong của một API cũ.

Các bước thực tế:

1. Xác định mức Java thấp nhất ứng dụng hỗ trợ.
2. Biên dịch với cấu hình phát hành phù hợp.
3. Chạy kiểm thử trên các runtime được hỗ trợ.
4. So tài liệu API của phiên bản nguồn và đích khi có khác biệt.
5. Đo lại những luồng nhạy cảm với độ trễ, bộ nhớ hoặc tải cao.
6. Khi phát hiện thay đổi, kiểm tra chương trình có dựa vào điều không được bảo đảm không.
7. Nếu vẫn có dấu hiệu vi phạm hợp đồng, tạo ví dụ tái hiện nhỏ và đối chiếu bản sửa lỗi/tài liệu của JDK.

Lệnh `javac --release 17` giúp kiểm tra mã với mức ngôn ngữ và API công khai tương ứng Java 17. Nó không làm lệnh `java` đang trỏ tới runtime khác tự biến thành Java 17.

Có thể kiểm tra công cụ đang dùng bằng:

```shell
javac --version
java --version
```

Kết quả phiên bản phụ thuộc môi trường nên không có một stdout cố định để chép làm kỳ vọng cho mọi máy.

Một bộ kiểm thử chạy thành công trên một runtime là bằng chứng cho lần kiểm thử ấy, không phải bằng chứng rằng mọi trường hợp không được đặc tả đã trở thành tương thích. Ngược lại, không nên mặc định mọi khác biệt đều là lỗi ứng dụng; cần kiểm tra đúng hợp đồng và dữ liệu đầu vào.

## 13. Chương trình Java 17 hoàn chỉnh

Chương trình sau chỉ in kết quả dựa trên hành vi được API bảo đảm. Lưu vào `ApiContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ApiContractDemo {
    private static int total(List<Integer> values) {
        int result = 0;
        for (int value : values) {
            result += value;
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> arrayList = new ArrayList<>(List.of(3, 1, 2));
        List<Integer> linkedList = new LinkedList<>(List.of(3, 1, 2));
        System.out.println("array total = " + total(arrayList));
        System.out.println("linked total = " + total(linkedList));
        System.out.println("same list contents = " + arrayList.equals(linkedList));

        List<String> factory = List.of("A", "B");
        try {
            factory.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("List.of is unmodifiable");
        }

        List<String> collected =
                Stream.of("A", "B").collect(Collectors.toList());
        System.out.println("collected contents = " + collected);

        ArrayList<String> editable =
                Stream.of("A", "B")
                      .collect(Collectors.toCollection(ArrayList::new));
        editable.add("C");
        System.out.println("explicit editable list = " + editable);

        List<String> streamList = Stream.of("A", "B").toList();
        try {
            streamList.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Stream.toList is unmodifiable");
        }

        Map<String, Integer> counts = new HashMap<>();
        counts.put("B", 2);
        counts.put("A", 1);
        System.out.println("explicit sorted keys = " + new TreeMap<>(counts));

        String[] sourceArray = {"A", "B"};
        List<String> fixed = Arrays.asList(sourceArray);
        fixed.set(0, "Z");
        System.out.println("backing array = " + Arrays.toString(sourceArray));
        try {
            fixed.add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("Arrays.asList is fixed-size");
        }

        List<String> original = new ArrayList<>(List.of("A"));
        List<String> snapshot = List.copyOf(original);
        original.add("B");
        System.out.println("original = " + original);
        System.out.println("copy contents = " + snapshot);

        ArrayList<String> reserved = new ArrayList<>(100);
        System.out.println("reserved list size = " + reserved.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ApiContractDemo.java
java ApiContractDemo
```

Stdout:

```text
array total = 6
linked total = 6
same list contents = true
List.of is unmodifiable
collected contents = [A, B]
explicit editable list = [A, B, C]
Stream.toList is unmodifiable
explicit sorted keys = {A=1, B=2}
backing array = [Z, B]
Arrays.asList is fixed-size
original = [A, B]
copy contents = [A]
reserved list size = 0
```

Cách đọc minh chứng:

1. `total` chỉ cần duyệt một danh sách số nguyên không chứa `null`; cả hai cách lưu đều cho tổng 6.
2. `List.equals` so nội dung và thứ tự, không yêu cầu cùng lớp triển khai.
3. `List.of` và `Stream.toList` từ chối việc thêm.
4. Kết quả `Collectors.toList` chỉ được đọc theo nội dung; chương trình không thử suy lớp hay quyền sửa từ quan sát.
5. Khi cần danh sách có thể sửa, chương trình yêu cầu `ArrayList` rõ ràng bằng `toCollection`.
6. Map băm được chuyển sang `TreeMap` trước khi in, nên thứ tự hiển thị có căn cứ.
7. `Arrays.asList` phản ánh thay đổi giá trị vào mảng nguồn nhưng không cho tăng kích thước.
8. `List.copyOf` không phản ánh việc thêm phần tử vào nguồn sau đó.
9. Dung lượng dự kiến 100 không làm kích thước danh sách thành 100.

Chương trình cố ý không in tên lớp nội bộ, không đọc capacity bằng reflection và không xác nhận thứ tự trực tiếp của `HashMap`.

## 14. Tự kiểm tra cách phân loại một phát biểu

| Phát biểu | Cách đánh giá |
| --- | --- |
| “`List` có thứ tự theo vị trí” | Thuộc hợp đồng mô hình danh sách |
| “Mọi `List` đều thêm được” | Sai; có thao tác sửa tùy chọn và danh sách không sửa được |
| “`Collectors.toList` luôn trả `ArrayList`” | Không được phương thức bảo đảm |
| “`Stream.toList` trong Java 17 trả danh sách không sửa được” | Có thể dựa vào |
| “`HashMap` đang in tăng dần nên nó là map có thứ tự” | Suy luận sai từ quan sát |
| “`ArrayList` có thể thay chính sách tăng dung lượng nhưng vẫn đáp ứng chi phí khấu hao đã công bố” | Phù hợp ranh giới giữa hợp đồng và triển khai |
| “Đổi thuật toán sắp cho phép bỏ tính ổn định mà API đã hứa” | Sai; tối ưu phải giữ đặc tả |
| “Không ném `ConcurrentModificationException` chứng minh truy cập đồng thời đúng” | Sai; fail-fast không phải đồng bộ |

## 15. Tự luyện

1. Một phương thức của ứng dụng phải trả danh sách cho người gọi thêm phần tử. Có nên chỉ gọi `Collectors.toList()` và dựa vào lớp quan sát được không?  
   **Gợi ý:** yêu cầu rõ một cấu trúc có thể sửa, chẳng hạn `toCollection(ArrayList::new)` hoặc bản sao `ArrayList`.

2. Kiểm thử thất bại sau nâng JDK vì thứ tự khóa của `HashMap` khác trước. Cần hỏi gì trước tiên?  
   **Gợi ý:** sản phẩm có thật sự yêu cầu thứ tự không; nếu có, thiết kế đã chọn API bảo đảm thứ tự đó chưa?

3. `List.copyOf(source) == source` đôi lúc đúng. Có đủ để kết luận phương thức không tạo kết quả đúng hợp đồng không?  
   **Đáp án:** không. Hợp đồng không buộc mọi lần gọi cấp phát một đối tượng khác.

4. Đọc nguồn thấy một tỷ lệ tăng dung lượng. Cần ghi chú thế nào cho đúng?  
   **Gợi ý:** gắn với bản nguồn cụ thể và phân biệt nó với bảo đảm hiệu năng công khai.

5. Tại sao cần cả biên dịch theo `--release` và chạy kiểm thử trên runtime đích?  
   **Đáp án:** chúng kiểm tra những khía cạnh khác nhau; mức API khi biên dịch không lựa chọn thay runtime sẽ thực thi.

Khi dùng một kiến thức về collection để quyết định thiết kế, hãy truy ngược xem nó đến từ hợp đồng công khai, ghi chú triển khai hay một lần đo. Cách phân loại này cho biết điều gì có thể giữ ổn định trong chương trình và điều gì cần xác minh lại khi môi trường thay đổi.
