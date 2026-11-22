# Ảnh hưởng của phần tử khả biến đến equals và hashCode của collection

Một danh sách có thể giữ nguyên đối tượng list, nguyên số phần tử và nguyên các tham chiếu, nhưng kết quả `equals` hoặc `hashCode` của nó vẫn thay đổi. Nguyên nhân nằm ở các đối tượng phần tử: collection có bình đẳng theo nội dung thường dựa vào bình đẳng và mã băm của những đối tượng đang được chứa.

Điều này quan trọng khi dùng collection làm khóa map, phần tử tập băm, bản chụp để so sánh thay đổi hoặc thành phần của một đối tượng giá trị. Chỉ bọc collection thành không cho sửa chưa chắc làm giá trị của nó ổn định.

Bài dùng Java 17, tập trung vào sự phụ thuộc từ phần tử khả biến đến giá trị bình đẳng và mã băm của cấu trúc chứa. Các đoạn Java ngắn chỉ minh họa cơ chế. Chương trình hoàn chỉnh ở phần thực nghiệm có lệnh biên dịch và kết quả chuẩn.

## 1. Trước hết, phân biệt ba lớp thay đổi

Giả sử `labels` là một `ArrayList<MutableLabel>` có một phần tử.

Ba thao tác khác nhau:

```java
labels.add(new MutableLabel("C"));
labels.set(0, new MutableLabel("B"));
labels.get(0).rename("B");
```

- `add` thêm phần tử, làm cấu trúc danh sách thay đổi.
- `set` thay phần tử gắn với một vị trí đang có.
- `rename` sửa trạng thái bên trong đối tượng mà danh sách đã tham chiếu.

Bài này quan tâm chủ yếu tới thao tác cuối. Danh sách có thể không nhận một lời gọi sửa nào, nhưng nội dung được dùng khi so sánh giá trị đã khác.

Sơ đồ:

```text
Trước:
    list ----> vị trí 0 ----> MutableLabel, text = "A"

Sau rename:
    cùng list -> cùng vị trí 0 -> cùng MutableLabel, text = "B"
```

Nếu `MutableLabel.equals` và `hashCode` dựa vào `text`, dữ liệu mà các phép toán của list sử dụng cũng đổi theo.

Cần tách hai câu hỏi:

1. Collection có thay đổi cấu trúc qua API không?
2. Giá trị bình đẳng hoặc mã băm của collection có còn như trước không?

Câu trả lời thứ nhất là “không” chưa suy ra câu thứ hai là “có”.

## 2. equals và hashCode của cấu trúc chứa phụ thuộc gì?

Không phải mọi `Collection` có cùng cách định nghĩa bình đẳng. Trước khi phân tích tính khả biến, cần biết hợp đồng cụ thể.

| Kiểu cấu trúc thông thường | Bình đẳng dựa vào | Mã băm dựa vào |
| --- | --- | --- |
| `List` | Cùng dãy phần tử theo thứ tự | Mã băm phần tử cùng vị trí trong dãy |
| `Set` | Cùng các thành viên theo hợp đồng tập hợp | Mã băm các thành viên |
| `Map` | Cùng các ánh xạ khóa–giá trị | Mã băm các entry, gồm khóa và giá trị |
| Cấu trúc chỉ dùng bình đẳng danh tính | Chính instance | Quy tắc danh tính hoặc hợp đồng lớp |
| Cấu trúc chuyên dụng khác | Phải đọc hợp đồng riêng | Phải đọc hợp đồng riêng |

Không lấy hành vi `List.equals` áp dụng cho mọi hàng đợi hoặc deque. Chẳng hạn, một lớp có thể tiếp tục dùng bình đẳng danh tính mặc định thay vì so nội dung.

Vì vậy, phát biểu chính xác là: **khi hợp đồng bình đẳng hoặc băm của cấu trúc phụ thuộc vào trạng thái phần tử, thay đổi trạng thái liên quan của phần tử có thể lan tới cấu trúc chứa**. Tài liệu [Collection Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html) cũng phân biệt khả năng sửa của collection với khả năng thay đổi của các đối tượng được chứa.

## 3. List: không đổi kích thước nhưng giá trị có thể đổi

### 3.1. Bình đẳng theo thứ tự và từng phần tử

Hai list bằng nhau khi có cùng kích thước và các cặp phần tử tương ứng bằng nhau theo hợp đồng list.

Giả sử:

```text
current   = [MutableLabel("A")]
baseline  = [MutableLabel("A")]
```

Hai phần tử là hai đối tượng độc lập, nhưng lớp định nghĩa bình đẳng theo trường `text`. Ban đầu, hai list bằng nhau.

Sau khi chỉ sửa phần tử của `current` thành `"B"`:

```text
current   = [MutableLabel("B")]
baseline  = [MutableLabel("A")]
```

Hai list không còn bằng nhau. Không có phần tử nào được thêm hoặc xóa.

Kết quả phản ánh trạng thái hiện tại, không phải giá trị lịch sử tại lúc list được tạo.

### 3.2. Cơ chế mã băm theo dãy

Hợp đồng `List.hashCode` dùng cách tích lũy theo thứ tự, có thể diễn đạt:

```java
int hash = 1;
for (E element : list) {
    hash = 31 * hash + (element == null ? 0 : element.hashCode());
}
```

Đây là mã giả theo kiểu Java để mô tả công thức, cần ngữ cảnh generic và list nếu muốn đưa vào một lớp.

Với list một phần tử mà phần tử có hash bằng mã băm chuỗi `"A"`:

```text
hash ban đầu = 31 × 1 + 65 = 96
```

Nếu phần tử chuyển sang dùng hash của `"B"`:

```text
hash sau sửa = 31 × 1 + 66 = 97
```

Ví dụ cụ thể này đổi mã băm. Nhưng không được kết luận mọi thay đổi giá trị đều làm hash khác: va chạm mã băm vẫn có thể xảy ra.

Công thức và quan hệ bình đẳng được quy định ở [List.equals và List.hashCode Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#hashCode()).

### 3.3. Thay đổi có thể ảnh hưởng cả contains và indexOf

Nếu `equals` của phần tử thay đổi, một truy vấn theo giá trị cũ có thể không còn tìm thấy, còn truy vấn theo giá trị mới có thể tìm thấy.

Với list thông thường, đây có thể là thay đổi hợp lệ của dữ liệu hiện tại. List không dựa vào bảng băm của phần tử để định vị vị trí giống như một tập băm.

Tuy vậy, ứng dụng vẫn phải xác định có được đổi trạng thái đó không. “Cấu trúc vẫn hoạt động theo hợp đồng” không chứng minh thao tác phù hợp nghiệp vụ.

## 4. Set: phân biệt hash của tập với tính hợp lệ của thành viên

### 4.1. Mã băm tập phụ thuộc mã băm thành viên

Hợp đồng `Set.hashCode` lấy tổng mã băm các phần tử, với quy tắc tương ứng cho `null` nếu được phép.

Vì tổng không phụ thuộc thứ tự, hai set bằng nhau có cùng mã băm dù thứ tự duyệt khác nhau. Tuy nhiên, nếu mã băm của thành viên đổi, mã băm tính cho toàn tập có thể đổi.

Đó là một lớp phụ thuộc về giá trị. Còn một vấn đề nghiêm trọng hơn: phần tử vẫn đang nằm trong chính cấu trúc dùng để quản lý thành viên.

### 4.2. Sửa phần tử đang ở HashSet có thể phá giả định tìm kiếm

Một tập băm dùng bình đẳng và mã băm để tổ chức phần tử. Khi phần tử được thêm, vị trí tìm kiếm được gắn với thông tin tại thời điểm đó.

Nếu sau đó setter đổi trường tham gia `equals` hoặc `hashCode`, tập không tự nhận setter rồi đưa phần tử sang vị trí phù hợp trạng thái mới.

Hợp đồng `Set` không xác định hành vi khi đối tượng đang thuộc tập bị sửa theo cách ảnh hưởng phép so sánh bình đẳng. Không đưa ra output bắt buộc như “contains chắc chắn luôn false” cho mọi tình huống đã phá điều kiện này. Nó có thể biểu hiện bằng tra cứu, xóa hoặc loại trùng không như mong đợi.

Phạm vi cần nhớ:

- Phần tử có thể vẫn xuất hiện khi duyệt.
- Điều đó không chứng minh việc định vị theo giá trị còn hợp lệ.
- Mã băm tính lại của set không tự sửa vị trí nội bộ của phần tử.
- Không đổi hash trong một trường hợp cụ thể cũng chưa đủ chứng minh an toàn nếu quan hệ bình đẳng đã đổi.

Xem [Set Java 17: phần tử khả biến và hợp đồng hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

### 4.3. Sửa trường không tham gia bình đẳng có thể không ảnh hưởng

Một `Item` có `id` bất biến và `label` thay đổi được, trong khi `equals`–`hashCode` chỉ dựa vào `id`, có thể đổi nhãn mà không đổi quan hệ bình đẳng hoặc mã băm.

Do đó, không phải cứ đối tượng có setter là mọi collection chứa nó chắc chắn đổi hash.

Phải hỏi **trường nào đổi và những phương thức nào phụ thuộc vào trường đó**. Nếu comparator, logic nghiệp vụ hoặc một chỉ mục khác dùng nhãn, chúng vẫn cần được xem xét riêng.

## 5. Map: giá trị khả biến cũng ảnh hưởng hash của toàn map

### 5.1. Hash của map không chỉ dựa vào khóa

Với map thông thường, `hashCode` được tính từ các entry. Mỗi entry có đóng góp từ cả khóa và giá trị, thường được diễn đạt theo hợp đồng entry bằng XOR mã băm khóa với mã băm giá trị; hash toàn map cộng các đóng góp entry.

Vì vậy:

```java
Map<String, MutableLabel> labels = new HashMap<>();
```

có thể có khóa ổn định nhưng hash của chính `labels` vẫn đổi khi đối tượng value đổi mã băm.

### 5.2. Hai map có thể ngừng bằng nhau dù tập khóa không đổi

Giả sử hai map có cùng khóa `"key"`, cùng gắn với hai giá trị độc lập đang bằng nhau.

Sửa value ở một map theo cách làm đổi `equals` có thể khiến hai map không còn bằng nhau. Cả hai vẫn có cùng một khóa; `size()` vẫn như cũ.

Không dùng “tập khóa không đổi” làm bằng chứng toàn map không đổi giá trị.

### 5.3. Phân biệt sửa value với sửa key

Nếu value thay đổi, việc tìm ánh xạ theo một khóa chuỗi ổn định trong `HashMap` vẫn có thể hoạt động đúng. Điều đang đổi là giá trị của ánh xạ, bình đẳng và mã băm của toàn map.

Nếu đối tượng key bị sửa ở phần ảnh hưởng bình đẳng hoặc băm, chính việc định vị ánh xạ có thể mất điều kiện hợp lệ.

Tài liệu [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) đặc biệt cảnh báo các khóa khả biến ảnh hưởng bình đẳng. Hai trường hợp này cần được phân tích riêng.

## 6. Thay đổi hash theo thời gian có vi phạm hợp đồng Object không?

Không nhất thiết.

Hợp đồng `Object.hashCode` yêu cầu tính nhất quán trong một lần chạy khi thông tin được dùng cho `equals` không bị thay đổi. Nó không yêu cầu hash của mọi đối tượng phải là một hằng số bất kể trạng thái.

Nếu một phần tử có bình đẳng theo trường `text` và trường đó được phép đổi, mã băm của phần tử có thể đổi theo. List chứa nó cũng có thể đổi mã băm khi trạng thái dùng để so sánh list thay đổi.

Vấn đề phát sinh khi ứng dụng đồng thời yêu cầu một điều mạnh hơn: đối tượng đang được dùng như khóa hoặc phần tử chỉ mục phải giữ tiêu chí định vị ổn định.

Phân biệt:

| Tình huống | Ý nghĩa |
| --- | --- |
| Một list dữ liệu hiện tại đổi equality sau khi phần tử đổi | Có thể là hành vi hợp lệ theo trạng thái |
| Hash của list đổi cùng thông tin equality | Không tự vi phạm hợp đồng hashCode |
| List đó đang được dùng làm khóa trong HashMap và bị sửa | Có thể phá giả định của map ngoài |
| Hai đối tượng bằng nhau có hash khác nhau ở cùng trạng thái | Vi phạm hợp đồng của equals–hashCode |
| Hai trạng thái khác nhau có cùng hash | Có thể chỉ là va chạm hợp lệ |

Không chữa vấn đề bằng cách bắt `hashCode` luôn trả một số đã lưu nếu `equals` vẫn dùng trạng thái hiện tại mà không có thiết kế phù hợp. Mã băm phải nhất quán với quan hệ bình đẳng được chọn.

Xem [Object.hashCode Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()).

## 7. Hiệu ứng lan truyền qua các cấu trúc lồng nhau

Một phụ thuộc có thể đi qua nhiều lớp:

```text
thuộc tính khả biến của đối tượng
        |
        v
equals/hashCode của phần tử
        |
        v
equals/hashCode của list bên trong
        |
        v
equals/hashCode của record hoặc đối tượng chứa list
        |
        v
equals/hashCode của collection bên ngoài
```

### 7.1. List trong list

Nếu một list ngoài chứa list trong, và bình đẳng của list trong thay đổi sau khi thêm phần tử hoặc sửa trạng thái liên quan, list ngoài cũng có thể thay đổi kết quả so sánh hoặc hash.

Không cần có lời gọi `outer.add`, `outer.set` hay `outer.remove`.

### 7.2. Record chứa một List

Ví dụ:

```java
record TagGroup(List<String> tags) {
}
```

Tham chiếu thành phần của record không thể gán lại theo cách thông thường sau khởi tạo. Nhưng đối tượng list mà `tags` trỏ tới vẫn có thể thay đổi.

Bình đẳng và mã băm được sinh cho record có thể phụ thuộc vào giá trị hiện tại của thành phần list. Sửa nội dung list có thể làm record thay đổi equality và hash; collection chứa record lại có thể chịu ảnh hưởng tiếp.

`record` không tự sao chép hoặc làm bất biến sâu các đối tượng thành phần. Xem [Record Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

### 7.3. Map làm value hoặc thành phần của một khóa

Một đối tượng khóa có trường map có thể có hash phụ thuộc cả các value khả biến ở sâu bên trong map đó.

Một biến top-level là `final` hoặc một trường không có setter chưa đủ chứng minh toàn đồ thị dữ liệu dùng trong equality là ổn định.

Cần lần theo đúng những nhánh dữ liệu mà `equals` và `hashCode` thực sự sử dụng.

### 7.4. Không tạo quan hệ tự tham chiếu tùy tiện

Một collection chứa chính nó hoặc vòng tham chiếu qua nhiều collection có thể khiến `equals`, `hashCode` hoặc các phép duyệt đệ quy không còn xác định tốt theo hợp đồng, hoặc không kết thúc như mong muốn.

Đừng dùng khả năng lưu tham chiếu tùy ý để suy ra các thuật toán bình đẳng nội dung sẽ tự xử lý mọi đồ thị có chu trình.

## 8. Collection làm khóa hoặc thành viên của cấu trúc băm ngoài

### 8.1. Rủi ro gián tiếp

Đoạn minh họa nguy hiểm:

```java
List<MutableLabel> key = new ArrayList<>(List.of(label));
Map<List<MutableLabel>, String> index = new HashMap<>();
index.put(key, "saved");

label.rename("changed");
```

Dòng cuối không gọi phương thức nào của `key` hoặc `index`. Nhưng nếu nó đổi bình đẳng và mã băm của `label`, nó có thể đổi hash của list làm khóa.

Map ngoài vẫn tổ chức ánh xạ theo trạng thái đã dùng trước đó; nó không tự tái lập chỉ mục khi một đối tượng ở sâu trong khóa được sửa.

Đây là lý do “không sửa list làm khóa” còn phải bao gồm không sửa phần dữ liệu bên trong ảnh hưởng equality của list đó.

### 8.2. Map làm phần tử của HashSet

Tình huống tương tự xảy ra khi một map được đặt vào `HashSet`, rồi value trong map bị sửa theo cách làm đổi hash.

Các khóa của map trong có thể hoàn toàn ổn định, nhưng hash của chính map trong đã khác; set ngoài mới là nơi chịu rủi ro định vị.

### 8.3. Không khẳng định mọi lời gọi chắc chắn cho cùng một lỗi

Sau khi vi phạm điều kiện ổn định của khóa hoặc thành viên, đừng dựng bài học dựa trên một kết quả tình cờ như:

- `contains` nhất định trả false.
- Thêm lại nhất định tăng size.
- Một lần xóa nhất định khắc phục được mọi trạng thái.

Kết quả còn phụ thuộc mã băm, va chạm, cấu trúc bên trong và trạng thái cụ thể. Điều cần chứng minh là điều kiện hợp đồng đã bị phá vỡ, không phải một output đặc thù phải xuất hiện trên mọi JDK.

Chương trình ở bài này chỉ chạy các thay đổi vẫn giữ đúng điều kiện của cấu trúc băm, và minh họa quy trình loại bỏ trước khi sửa.

## 9. Unmodifiable, copy và final bảo vệ đến đâu?

### 9.1. final chỉ giữ tham chiếu

`final List<MutableLabel> labels` ngăn gán lại biến `labels`; nó không khóa cấu trúc list hoặc các trường của phần tử.

### 9.2. View không cho sửa vẫn nhìn thấy nguồn

`Collections.unmodifiableList(source)` hạn chế thao tác sửa qua wrapper. Nguồn vẫn có thể được sửa qua tham chiếu khác; các phần tử cũng có thể bị thay đổi.

Bình đẳng hoặc hash quan sát qua view có thể đổi theo dữ liệu nền.

### 9.3. Bản sao nông tách cấu trúc, không tách phần tử

Với:

```java
List<MutableLabel> copy = new ArrayList<>(source);
```

thêm hoặc thay phần tử ở nguồn không tự sửa cấu trúc `copy`. Nhưng sửa đối tượng mà cả hai cùng tham chiếu có thể làm equality và hash của cả hai cùng đổi.

Từ đó có một bẫy khi phát hiện thay đổi:

```text
tạo shallow copy làm baseline
sửa phần tử dùng chung
so source với baseline
kết quả vẫn bằng nhau
```

Không phải vì dữ liệu chưa đổi, mà vì cả hai phía đã cùng nhìn trạng thái mới của một đối tượng.

### 9.4. List.copyOf không phải ảnh chụp sâu của giá trị

`List.copyOf(source)` cho list không cho sửa với các phần tử của nguồn tại thời điểm gọi. Thay đổi cấu trúc nguồn không được phản ánh như một live view.

Tuy nhiên, đối tượng phần tử vẫn có thể là những tham chiếu được chia sẻ. Nếu phần tử sửa được và equality theo trạng thái, kết quả `copyOf` vẫn có thể thay đổi giá trị quan sát được.

Vì vậy, dùng `List.copyOf` không tự làm collection an toàn để làm khóa băm nếu phần tử dùng trong equality còn thay đổi.

### 9.5. Bất biến sâu cần được thiết kế

Một bản chụp có thể tạo từ các đối tượng giá trị bất biến, hoặc trích ra những thuộc tính bất biến cần giữ.

Không cần sao chép mọi trường của hệ thống một cách máy móc. Cần sao chép đúng phần dữ liệu mà bản chụp phải đại diện, đồng thời bảo đảm phần đó không bị đổi qua alias về sau.

Với một nhãn lưu bằng `String`, lấy giá trị chuỗi hiện tại vào list mới có thể đủ cho bản chụp nhãn. Với cấu trúc lồng sâu hơn, cần kiểm tra từng tầng.

## 10. Phần tử khả biến không luôn làm equality hoặc hash đổi

### 10.1. Trường bị sửa không tham gia bình đẳng

Nếu equality và hash chỉ dựa trên `id` ổn định, thay `displayName` có thể không đổi kết quả collection.

Phải xét đúng hợp đồng. Việc đổi `toString()` hoặc output hiển thị không chứng minh equality đã đổi.

### 10.2. Phần tử dùng bình đẳng danh tính

Một lớp không override bình đẳng theo trạng thái có thể giữ `equals` và `hashCode` dựa trên danh tính mặc định. Sửa một trường thông thường không tự làm nó trở thành đối tượng khác.

Chẳng hạn, các đối tượng có nội dung thay đổi nhưng không định nghĩa `equals` theo nội dung không tự được collection so sánh bằng nội dung mới.

Mảng cũng không tự cung cấp bình đẳng nội dung qua `Object.equals`. Thay phần tử của một mảng đang được tham chiếu không được hiểu như thay một giá trị sâu trong công thức list nếu list chỉ nhìn mảng theo bình đẳng danh tính.

Nếu ứng dụng cần so nội dung sâu, phải dùng hoặc thiết kế phép đối chiếu phù hợp.

### 10.3. Có va chạm mã băm

Ngay cả khi equality theo trạng thái đổi, hash có thể trùng giữa hai trạng thái.

Do đó:

```text
hash trước == hash sau
```

không chứng minh đối tượng hoặc collection không thay đổi.

Chiều hữu ích hơn: nếu cùng một phép tính hash đúng hợp đồng trên hai trạng thái cho kết quả khác nhau, chúng không thể được coi là bằng nhau theo cùng hợp đồng tại những trạng thái đó. Nhưng vẫn không dùng hash như một bản ghi lịch sử đầy đủ.

## 11. Chiến lược thiết kế an toàn

### 11.1. Dùng định danh ổn định cho cấu trúc tra cứu

Thay vì dùng toàn bộ collection đang thay đổi làm khóa, có thể dùng một mã định danh bất biến có ý nghĩa nghiệp vụ.

Ví dụ, map quản lý giỏ hàng theo `cartId`, còn danh sách món hàng là value. Giỏ thay đổi không buộc thay hash của khóa.

Chọn định danh phải đúng yêu cầu: một mã định danh không thay thế nội dung khi mục tiêu thật sự là đối chiếu hai bản chụp giá trị.

### 11.2. Dùng giá trị bất biến cho khóa theo nội dung

Nếu khóa thật sự cần dựa trên nội dung, tạo một biểu diễn bất biến của nội dung cần định vị.

Với dữ liệu có cấu trúc lồng, chỉ bọc lớp ngoài là chưa đủ. Cần bảo đảm mọi thành phần tham gia equality và hash giữ ổn định trong thời gian khóa còn được dùng.

### 11.3. Loại khỏi chỉ mục trước khi sửa rồi thêm lại

Nếu cho phép cập nhật đối tượng dùng làm thành viên hoặc khóa, quy trình có thể là:

1. Tìm và loại đối tượng khi nó vẫn giữ trạng thái cũ hợp lệ.
2. Kiểm tra đã loại thành công.
3. Thay trạng thái.
4. Đưa lại vào các chỉ mục liên quan.
5. Xử lý trường hợp trạng thái mới trùng giá trị đã có.

Không đổi trước rồi mới cố xóa bằng trạng thái mới. Khi đã đổi, chính thao tác tìm để xóa có thể không còn đáng tin theo hợp đồng.

Nếu đối tượng nằm trong nhiều chỉ mục hoặc có nhiều luồng truy cập, cả chuỗi phải được tổ chức nhất quán. Xóa ở một nơi không đủ nếu nơi khác vẫn dùng nó làm khóa.

### 11.4. Tạo baseline có ý nghĩa

Để phát hiện thay đổi, baseline cần đại diện trạng thái trước, không tiếp tục trỏ đến những phần tử đang được sửa.

Có thể lưu:

- Bản chụp các thuộc tính giá trị cần so.
- Đối tượng giá trị bất biến.
- Số phiên bản hoặc dấu hiệu thay đổi do ứng dụng quản lý.
- Một bản sao phần tử phù hợp mô hình dữ liệu.

Không dùng riêng `hashCode` làm dấu vân tay không va chạm hoặc thay thế bản chụp đầy đủ. Hash của collection là một số nguyên phục vụ hợp đồng băm, không phải checksum bảo mật.

### 11.5. Không lưu cache hash tùy tiện

Lưu hash tính một lần có thể phù hợp với đối tượng bất biến được thiết kế đúng. Với dữ liệu vẫn thay đổi và equality dùng trạng thái mới, giữ hash cũ có thể làm các đối tượng bằng nhau có mã băm khác nhau.

Muốn cache phải có bất biến hoặc cơ chế vô hiệu hóa bảo đảm nhất quán với equality, không phải chỉ để tránh triệu chứng “hash đổi”.

## 12. Chương trình Java hoàn chỉnh

Chương trình kiểm tra những thay đổi vẫn hợp lệ: phần tử khả biến ở trong list, value khả biến ở trong map có khóa ổn định, trường mô tả không tham gia equality và một chuỗi cập nhật chỉ mục có remove trước mutation.

Lưu vào tệp `MutableElementEqualityDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class MutableElementEqualityDemo {
    static final class MutableLabel {
        private String text;

        MutableLabel(String text) {
            this.text = Objects.requireNonNull(text);
        }

        String text() {
            return text;
        }

        void rename(String text) {
            this.text = Objects.requireNonNull(text);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableLabel that
                    && text.equals(that.text);
        }

        @Override
        public int hashCode() {
            return text.hashCode();
        }

        @Override
        public String toString() {
            return text;
        }
    }

    static final class Item {
        private final String id;
        private String label;

        Item(String id, String label) {
            this.id = Objects.requireNonNull(id);
            this.label = Objects.requireNonNull(label);
        }

        void rename(String label) {
            this.label = Objects.requireNonNull(label);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Item that && id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    record TagGroup(List<String> tags) {
    }

    public static void main(String[] args) {
        MutableLabel label = new MutableLabel("A");
        List<MutableLabel> current = new ArrayList<>(List.of(label));
        List<MutableLabel> independent =
                List.of(new MutableLabel("A"));
        List<MutableLabel> shallow = new ArrayList<>(current);
        List<MutableLabel> unmodifiable = List.copyOf(current);
        List<String> frozenValues = List.of(label.text());

        int initialHash = current.hashCode();
        System.out.println("before equals: " + current.equals(independent));
        System.out.println("before list hash: " + initialHash);

        label.rename("B");

        System.out.println("same list size: " + (current.size() == 1));
        System.out.println("after equals: " + current.equals(independent));
        System.out.println("after list hash: " + current.hashCode());
        System.out.println("shallow copy follows: " + shallow);
        System.out.println("unmodifiable copy follows: " + unmodifiable);
        System.out.println("shallow equals current: " + shallow.equals(current));
        System.out.println("frozen values: " + frozenValues);

        MutableLabel value = new MutableLabel("X");
        Map<String, MutableLabel> map = new HashMap<>();
        map.put("key", value);
        Map<String, MutableLabel> expectedMap =
                Map.of("key", new MutableLabel("X"));
        int mapHash = map.hashCode();

        value.rename("Y");
        System.out.println("map key still present: " + map.containsKey("key"));
        System.out.println("map equals baseline: " + map.equals(expectedMap));
        System.out.println("map hash changed: " + (mapHash != map.hashCode()));

        Item item = new Item("P1", "Old label");
        Set<Item> items = new HashSet<>(List.of(item));
        Set<Item> expectedItems = Set.of(new Item("P1", "Other label"));
        int setHash = items.hashCode();
        item.rename("New label");
        System.out.println("ignored field keeps set equals: "
                + items.equals(expectedItems));
        System.out.println("ignored field keeps set hash: "
                + (setHash == items.hashCode()));

        List<String> tags = new ArrayList<>(List.of("A"));
        TagGroup group = new TagGroup(tags);
        TagGroup expectedGroup = new TagGroup(List.of("A"));
        List<TagGroup> outer = List.of(group);
        List<TagGroup> expectedOuter = List.of(expectedGroup);
        int outerHash = outer.hashCode();
        tags.set(0, "B");
        System.out.println("nested record equals baseline: "
                + group.equals(expectedGroup));
        System.out.println("outer list equals baseline: "
                + outer.equals(expectedOuter));
        System.out.println("outer list hash changed: "
                + (outerHash != outer.hashCode()));

        List<String> key = new ArrayList<>(List.of("A"));
        Set<List<String>> index = new HashSet<>();
        index.add(key);
        boolean removed = index.remove(key);
        key.add("B");
        boolean addedAgain = index.add(key);
        System.out.println("remove before mutation: " + removed);
        System.out.println("reinsert after mutation: " + addedAgain);
        System.out.println("index contains new value: "
                + index.contains(List.of("A", "B")));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 MutableElementEqualityDemo.java
java MutableElementEqualityDemo
```

Kết quả chuẩn:

```text
before equals: true
before list hash: 96
same list size: true
after equals: false
after list hash: 97
shallow copy follows: [B]
unmodifiable copy follows: [B]
shallow equals current: true
frozen values: [A]
map key still present: true
map equals baseline: false
map hash changed: true
ignored field keeps set equals: true
ignored field keeps set hash: true
nested record equals baseline: false
outer list equals baseline: false
outer list hash changed: true
remove before mutation: true
reinsert after mutation: true
index contains new value: true
```

### 12.1. List giữ size nhưng giá trị đổi

`MutableLabel` tính equality và hash theo `text`. Khi đổi từ `A` sang `B`, `current` vẫn có một phần tử nhưng không còn bằng baseline độc lập.

Hai giá trị hash 96 và 97 đến từ dữ liệu cụ thể cùng công thức list, không phải ví dụ về mọi mutation luôn đổi hash.

### 12.2. Bản sao nông làm baseline trôi theo nguồn

`shallow` và `unmodifiable` giữ cùng đối tượng `MutableLabel`, nên in `[B]`. `shallow.equals(current)` vẫn là `true`.

`frozenValues` giữ chuỗi nhãn `"A"` được lấy trước khi setter chạy. `String` bất biến và setter đã gán nhãn mới cho đối tượng, nên bản chụp này vẫn là `[A]`.

### 12.3. Map có khóa ổn định nhưng hash toàn map đổi

Giá trị `MutableLabel` chuyển từ `X` sang `Y`. Map vẫn tìm được khóa `"key"`, nhưng không còn bằng baseline map có value độc lập `X`; hash của toàn map cũng đổi trong dữ liệu này.

Điều đó không phải lỗi tra cứu khóa của map trong. Nó trở thành rủi ro khác nếu chính map này đang được dùng làm khóa hoặc thành viên ở một cấu trúc ngoài.

### 12.4. Trường ngoài tiêu chí equality không đổi set

`Item` chỉ dùng `id` bất biến trong equality và hash. Đổi nhãn không ảnh hưởng hai phương thức đó.

Vì vậy, phần thử nghiệm này không vi phạm điều kiện ổn định của phần tử tập băm. Nó minh họa vì sao phải phân tích quan hệ phụ thuộc, không chỉ thấy setter là kết luận hash đổi.

### 12.5. Record không khóa list thành phần

`TagGroup` giữ tham chiếu tới `tags`. `tags.set(0, "B")` đổi bình đẳng của list, rồi đổi bình đẳng của record và list ngoài chứa record.

Trong chương trình, các đối tượng này không đang nằm trong chỉ mục băm cần giữ giá trị ổn định, nên việc thay đổi equality theo trạng thái được quan sát một cách hợp lệ.

### 12.6. Remove trước mutation giữ chỉ mục đúng

Phần cuối loại `key` khỏi set trước khi thêm `B` vào list. Sau đó đưa lại và tra cứu bằng một list khác cùng nội dung.

Ví dụ một luồng này chỉ minh họa thứ tự thao tác đúng. Nó chưa giải quyết giao dịch nhiều chỉ mục hoặc truy cập đồng thời.

## 13. Iterator không phải bộ giám sát mọi thay đổi giá trị

Setter của phần tử thường không cập nhật bộ đếm sửa cấu trúc của collection. Không có lý do để mong đợi một `ConcurrentModificationException` xuất hiện chỉ vì hash của phần tử đã đổi.

Từ đó:

- Iterator tiếp tục chạy không chứng minh giá trị collection không đổi.
- `size()` giữ nguyên không chứng minh hash ổn định.
- Một collection hỗ trợ truy cập đồng thời không tự làm các phần tử bên trong an toàn.
- Một thao tác so sánh đang chạy trong lúc dữ liệu liên quan bị đổi cần bảo đảm đồng bộ hoặc bản chụp riêng.

Nếu một luồng tính hash trong khi luồng khác sửa các trường dùng cho equality, ứng dụng có thể không quan sát một trạng thái nghiệp vụ nhất quán. Đừng dùng bình đẳng hoặc mã băm làm cơ chế đồng bộ.

## 14. Cách rà soát một cấu trúc dữ liệu thực tế

Khi collection có phần tử khả biến, hãy đi theo chuỗi câu hỏi:

1. Kiểu collection cụ thể định nghĩa equality và hash ra sao?
2. Phương thức của nó sử dụng equality hoặc hash của phần tử, khóa hay value nào?
3. Những thuộc tính nào của các đối tượng đó có thể đổi?
4. Có thuộc tính bị đổi nằm ngoài tiêu chí equality không?
5. Có list, map, record hoặc đối tượng chứa lồng nhiều tầng không?
6. Có alias cho phép sửa từ một thành phần khác không?
7. Collection đang chỉ là dữ liệu hiện tại, hay đang làm khóa hoặc thành viên một chỉ mục?
8. Baseline so sánh có thật sự độc lập về phần trạng thái cần giữ không?
9. Wrapper chỉ đọc có đang bị nhầm với bất biến sâu không?
10. Thay đổi có được tổ chức lại ở mọi chỉ mục liên quan không?
11. Có nhiều luồng làm mất tính nhất quán của thời điểm quan sát không?
12. Kiểm thử có đang dựa vào một hành vi không được bảo đảm sau khi đã phá hợp đồng không?

Mục tiêu là xác định đường lan truyền của thay đổi, thay vì chỉ nhìn kiểu khai báo hoặc một lời gọi setter riêng lẻ.

## 15. Bài tập tự kiểm chứng

### Bài 1: Hash list thay đổi do phần tử

Tạo hai list độc lập cùng chứa một nhãn `"A"`. Lớp nhãn dùng nội dung chuỗi cho equality và hash.

Đổi nhãn ở một phía sang `"B"`. Kiểm tra size, tham chiếu phần tử, equality giữa hai list và hash trước–sau.

Giải thích vì sao hash thay đổi không đòi hỏi list phải nhận lời gọi thêm hoặc xóa.

### Bài 2: Baseline bị dùng chung

Tạo baseline bằng `new ArrayList<>(source)`, rồi sửa một phần tử được chia sẻ.

Chứng minh so sánh hai list vẫn có thể trả `true` dù dữ liệu đã đổi so với trạng thái ban đầu. Sau đó thay baseline bằng bản chụp các giá trị bất biến cần giữ.

### Bài 3: Map value và Map key

Thiết kế hai tình huống:

- Value thay đổi nhưng khóa chuỗi ổn định.
- Một đối tượng khả biến được dùng làm key và bị đổi trường equality.

Tình huống đầu có thể quan sát bình đẳng hoặc hash toàn map đổi mà tra cứu khóa vẫn đúng. Tình huống sau phải được xác định là vi phạm điều kiện ổn định của khóa; không yêu cầu một output lỗi cố định cho mọi JDK.

### Bài 4: Trường nào thật sự ảnh hưởng?

Một lớp có `id`, `displayName` và `lastViewedAt`. Chọn `id` làm tiêu chí equality cùng hash.

Kiểm tra đổi hai trường còn lại có ảnh hưởng equality hoặc hash của list, set chứa nó không. Sau đó giải thích vì sao thay đổi cách hiển thị không phải bằng chứng bình đẳng đã đổi.

### Bài 5: Collection lồng trong record

Tạo record chứa list chuỗi, rồi đặt record trong list ngoài. Thay một chuỗi bằng `set` trên list thành phần.

Theo dõi từng tầng phụ thuộc. Thiết kế lại constructor hoặc mô hình dữ liệu để có một bản chụp bất biến phù hợp, không chỉ một tham chiếu thành phần final.

### Bài 6: Cập nhật thành viên chỉ mục

Một đối tượng cần đổi giá trị khi đang ở nhiều tập băm hoặc map. Vẽ quy trình loại khỏi mọi chỉ mục liên quan, sửa, kiểm tra xung đột và thêm lại.

Nêu cách ngăn bên đọc thấy trạng thái trung gian nếu yêu cầu nghiệp vụ đòi hỏi nhất quán.

## 16. Các kết luận cần tránh

- “Không đổi size thì equals và hashCode không đổi.”
- “Phần tử còn cùng tham chiếu thì giá trị collection vẫn như cũ.”
- “Hash đổi theo trạng thái luôn vi phạm Object.hashCode.”
- “Hash không đổi chứng minh dữ liệu chưa đổi.”
- “List.copyOf tạo bản sao sâu.”
- “Record có thành phần final nên equality luôn bất biến.”
- “Chỉ cần không gọi set hoặc add trên list làm khóa là đủ an toàn.”
- “Hash của map chỉ phụ thuộc khóa.”
- “Sửa mọi trường của phần tử luôn làm hash collection đổi.”
- “Không có ConcurrentModificationException nghĩa là chỉ mục vẫn đúng.”

Nguyên tắc cần giữ là theo dõi toàn bộ dữ liệu tham gia equality và hash, kể cả những đối tượng ở sâu bên trong. Giá trị có thể thay đổi hợp lệ theo thời gian; khi nó được dùng để định vị trong một cấu trúc khác, ứng dụng phải bảo đảm sự ổn định hoặc cập nhật chỉ mục theo một quy trình đúng.
