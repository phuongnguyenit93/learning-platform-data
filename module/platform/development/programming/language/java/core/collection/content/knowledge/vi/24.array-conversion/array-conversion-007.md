# Chuyển Map sang danh sách entry, khóa hoặc giá trị

## 1. Chọn thông tin cần giữ trước khi chọn câu lệnh

`Map<K, V>` biểu diễn quan hệ từ khóa tới giá trị. `List<T>` biểu diễn một dãy phần tử có chỉ số. Khi chuyển từ Map sang danh sách, câu hỏi đầu tiên là **mỗi phần tử của danh sách cần chứa điều gì**.

Ví dụ một bảng điểm:

~~~text
B -> 20
A -> 10
C -> 20
~~~

Có ba kết quả khác mục đích:

| Kết quả | Dữ liệu minh họa | Thông tin còn giữ |
| --- | --- | --- |
| Danh sách khóa | `[B, A, C]` | Những mã nào đang tồn tại |
| Danh sách giá trị | `[20, 10, 20]` | Những điểm số đang được lưu, kể cả điểm trùng |
| Danh sách entry | `[B=20, A=10, C=20]` | Từng cặp mã và điểm đi cùng nhau |

Một entry là một cặp khóa–giá trị, được biểu diễn bằng `Map.Entry<K, V>`. Giữ entry giúp sắp xếp hoặc lọc cả dòng mà không làm mất việc điểm nào thuộc mã nào.

Nếu chỉ lấy giá trị rồi bỏ khóa, ta không thể tự suy ra rằng điểm `20` là của `B` hay `C`. Nếu lấy riêng khóa rồi sắp xếp mà không điều chỉnh dữ liệu tương ứng, việc ghép lại theo chỉ số có thể tạo những cặp chưa từng tồn tại trong Map.

Sau khi chọn phần thông tin cần giữ, cần quyết định thêm ba điều: thứ tự mong muốn, danh sách có được sửa hay không, và dữ liệu cần tách khỏi Map ở mức nào. Đây là các quyết định độc lập; một danh sách không cho thêm/xóa vẫn có thể chứa những đối tượng phần tử thay đổi được.

## 2. Ba khung nhìn của Map là nguồn để chuyển đổi

`Map` cung cấp ba khung nhìn:

~~~java
Set<K> keys = map.keySet();
Collection<V> values = map.values();
Set<Map.Entry<K, V>> entries = map.entrySet();
~~~

Đây là minh họa kiểu dữ liệu, không phải một chương trình độc lập; `K`, `V` và `map` thuộc ngữ cảnh khai báo của ứng dụng.

Các phương thức trên trả về những khung nhìn dùng chung Map nền. Nếu Map thay đổi, kết quả quan sát qua khung nhìn cũng thay đổi. Các thao tác xóa được hỗ trợ trên khung nhìn có thể xóa ánh xạ tương ứng khỏi Map. [Java SE 17 — Map collection views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#keySet()).

Cần phân biệt:

~~~java
Set<String> keyView = scores.keySet();
List<String> keyList = new ArrayList<>(scores.keySet());
~~~

`keyView` vẫn là khung nhìn của `scores`. `keyList` có cấu trúc danh sách riêng, được điền bằng những khóa được duyệt lúc tạo.

Trong các ví dụ của bài, Map không bị sửa đồng thời trong lúc chuyển đổi. Nếu không giữ điều kiện này, không nên gọi mọi phép chép là “ảnh chụp tại cùng một thời điểm” mà chưa xem hợp đồng đồng thời của nguồn.

### Map không trực tiếp là Collection

Không thể dùng `new ArrayList<>(map)` như thể Map là một tập các phần tử thuộc một kiểu duy nhất. Hàm tạo từ collection cần nhận một `Collection`; Map cung cấp các khung nhìn để người viết chọn rõ cần khóa, giá trị hay entry.

`Arrays.asList(map)` cũng không phải phép trải Map thành các cặp. Với lời gọi một đối số như vậy, danh sách chứa một phần tử là chính đối tượng Map. Nó giải quyết một yêu cầu khác.

Hãy chọn một trong ba đường đi sau:

~~~text
Map<K,V>
   |-- keySet()  ------> danh sách K
   |-- values()  ------> danh sách V
   |-- entrySet() -----> danh sách cặp K,V
~~~

## 3. Danh sách khóa: sao chép các khóa đã có

Với một `Map<String, Integer>`:

~~~java
List<String> keys = new ArrayList<>(scores.keySet());
~~~

Danh sách chứa các tham chiếu khóa theo thứ tự nguồn được duyệt. Nếu Map nguồn là `LinkedHashMap` theo thứ tự chèn `B`, `A`, `C`, kết quả là `[B, A, C]`.

Sau khi chép:

- `keys.remove("B")` chỉ bỏ phần tử trong danh sách, không xóa khóa `B` của `scores`.
- `keys.add("X")` chỉ thêm vào danh sách, không tạo ánh xạ `X` trong Map.
- Nếu Map có thêm khóa `D`, danh sách đã chép không tự xuất hiện `D`.
- Có thể sắp xếp danh sách mà không sắp xếp lại cấu trúc Map.

Việc Map có khóa duy nhất không biến danh sách kết quả thành một `Set`. Sau khi đã có `ArrayList` riêng, người dùng vẫn có thể thêm một khóa trùng vào danh sách. Tính duy nhất của nguồn mô tả dữ liệu ban đầu; nó không trở thành quy tắc cấm phần tử trùng của mọi cấu trúc được tạo từ nguồn.

Sự độc lập ở đây nằm ở **các vị trí của danh sách**, không nhất thiết ở toàn bộ đối tượng khóa. Nếu khóa là một đối tượng sửa được, danh sách và Map vẫn giữ tham chiếu tới cùng đối tượng ấy. Đặc biệt, sửa khóa theo cách ảnh hưởng đến `equals` hoặc `hashCode` khi nó đang nằm trong Map có thể phá vỡ giả định của cấu trúc tìm kiếm. Chuyển sang danh sách không làm việc sửa khóa đó trở nên an toàn.

Khi chỉ cần danh sách mã để đưa vào một bộ chọn trên giao diện, đây thường là phép chuyển đơn giản và đúng thông tin. Nếu còn phải hiện tên hoặc điểm đi kèm từng mã, nên giữ cặp ngay từ đầu thay vì liên tục suy đoán quan hệ theo chỉ số.

## 4. Danh sách giá trị: giữ cả những giá trị trùng nhau

Cách tạo tương ứng:

~~~java
List<Integer> values = new ArrayList<>(scores.values());
~~~

Với ba ánh xạ `B=20`, `A=10`, `C=20`, danh sách có ba phần tử `[20, 10, 20]`. `values()` là một `Collection<V>` vì nhiều khóa có thể ánh xạ tới những giá trị bằng nhau.

Nếu tự đưa kết quả qua một `Set`, hai lần xuất hiện của `20` có thể bị gộp. Đó là một phép đổi ý nghĩa dữ liệu, không phải bước bắt buộc để chuyển Map thành danh sách.

Danh sách giá trị phù hợp khi cần tính tổng, thống kê hoặc chuyển dữ liệu sang một hàm chỉ làm việc với điểm số. Nhưng nó đã bỏ thông tin khóa. Muốn loại đúng học viên `B`, không nên chỉ xóa một phần tử `20` rồi cho rằng đã chỉ định được `B`.

Cũng cần tách phép sửa hai đối tượng sau:

~~~java
scores.values().remove(20);
values.remove(Integer.valueOf(20));
~~~

Dòng đầu, khi khung nhìn hỗ trợ xóa, yêu cầu xóa một ánh xạ có giá trị tương ứng trong Map; không nên dùng nó để chọn một khóa cụ thể khi nhiều khóa cùng giá trị. Dòng sau xóa trong danh sách `values` đã sao chép và không xóa ánh xạ của Map.

Tham số `Integer.valueOf(20)` ở dòng sau chọn overload xóa theo đối tượng. Với `List<Integer>`, `remove(20)` dùng tham số `int` sẽ chọn xóa theo chỉ số `20`, là một ý nghĩa khác.

Giá trị `null` cũng là dữ liệu nếu Map cho phép. `new ArrayList<>(map.values())` giữ giá trị đó trong danh sách. Nếu một bước xử lý sau không chấp nhận `null`, cần có quy tắc rõ ràng: giữ, thay thế, lọc bỏ hay báo lỗi; đừng để việc đổi cấu trúc âm thầm quyết định thay ứng dụng.

## 5. Danh sách entry: phải tách cấu trúc danh sách và đối tượng entry

### 5.1. Câu lệnh ngắn chỉ sao chép các tham chiếu entry

Cách viết thường thấy:

~~~java
List<Map.Entry<String, Integer>> entries =
        new ArrayList<>(scores.entrySet());
~~~

Câu lệnh tạo một danh sách riêng. Thêm/xóa các vị trí trong danh sách không tự thêm/xóa các ánh xạ của Map. Tuy nhiên, hàm tạo `ArrayList` không tự tạo một cặp khóa–giá trị độc lập cho từng entry; nó chép những đối tượng phần tử mà nguồn cung cấp.

Vì vậy, không được diễn giải câu lệnh này thành “các khóa và giá trị đã được đóng băng độc lập khỏi Map”. Cũng không được cho rằng việc bọc danh sách bằng một lớp chỉ đọc sẽ tự thay thế mọi entry bên trong bằng entry độc lập.

Hợp đồng Java 17 đặt giới hạn đáng chú ý cho entry lấy từ quá trình duyệt `entrySet`: sự kết nối với Map chỉ được xác định trong thời gian duyệt; hành vi ngoài quá trình ấy hoặc sau những thay đổi nền không được cho phép có thể không xác định. Muốn giữ cặp để dùng về sau, hãy tạo bản sao entry độc lập. [Java SE 17 — Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).

Điều này còn có nghĩa không nên viết một phép thử bằng một loại Map cụ thể rồi nâng kết quả thành hợp đồng chung. Một entry có thể trông như vẫn phản ánh giá trị mới trên một cách cài đặt, nhưng đó chưa phải bảo đảm cho mọi Map hoặc cho mọi thay đổi tiếp theo.

### 5.2. Bản sao độc lập bằng Map.Entry.copyOf

Với khóa và giá trị không `null`, Java 17 cho phép:

~~~java
List<Map.Entry<String, Integer>> entries = scores.entrySet().stream()
        .map(Map.Entry::copyOf)
        .toList();
~~~

Phần `map(Map.Entry::copyOf)` có vai trò khác với phần `toList()`:

- `copyOf` tạo biểu diễn entry không liên kết với Map nền và không hỗ trợ thay giá trị bằng `setValue`.
- `toList` gom các entry đó vào một danh sách không cho sửa qua các phương thức thay đổi danh sách.

`Map.Entry.copyOf` có từ Java 17, không nhận entry `null`, khóa `null` hoặc giá trị `null`. Nó không bảo đảm luôn cấp phát một đối tượng entry mới nếu đầu vào đã là loại bản sao phù hợp; điều cần dùng là hợp đồng độc lập với Map, không phải so sánh danh tính đối tượng.

Nếu muốn danh sách có thể thêm/xóa hoặc sắp xếp tại chỗ, chọn đích tường minh:

~~~java
List<Map.Entry<String, Integer>> entries = scores.entrySet().stream()
        .map(Map.Entry::copyOf)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Danh sách ở đây sửa được, nhưng từng entry bên trong vẫn không cho `setValue`. Không có mâu thuẫn: một quyền thuộc danh sách, quyền kia thuộc đối tượng phần tử.

### 5.3. Cặp độc lập có cho sửa giá trị hay không?

Có thể tạo một entry độc lập bằng `AbstractMap.SimpleEntry`:

~~~java
Map.Entry<String, Integer> local =
        new AbstractMap.SimpleEntry<>("B", 20);
local.setValue(25);
~~~

Entry `local` trở thành `B=25`. Vì nó không liên kết với `scores`, lời gọi này không cập nhật Map. Đây là lựa chọn khi ứng dụng cần một cặp có thể sửa trước khi quyết định ghi vào nơi khác. [Java SE 17 — SimpleEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleEntry.html).

Nếu entry độc lập đã được sửa, muốn lưu lại thay đổi thì cần một thao tác Map tường minh như `scores.put(local.getKey(), local.getValue())`, cùng quy tắc xử lý xung đột phù hợp. Tạo danh sách làm việc không tự xây dựng một cơ chế đồng bộ hai chiều.

Ngược lại, trong lúc đang duyệt `entrySet`, entry của một Map hỗ trợ cập nhật có thể dùng `setValue` để ghi trở lại Map. Chương trình đầy đủ minh họa cách này ngay trong vòng duyệt và không giữ entry sống để dùng sau đó.

## 6. Map có null: chọn dạng bản sao phù hợp

`LinkedHashMap` có thể chứa khóa `null` và giá trị `null`. Nếu dùng `Map.Entry.copyOf` cho mọi entry của nó, quá trình chuyển đổi sẽ ném `NullPointerException` khi gặp phần tương ứng.

Không nên đổi dữ liệu `null` sang chuỗi `"null"` chỉ để tránh lỗi, vì hai giá trị có ý nghĩa khác nhau. Có thể dùng `AbstractMap.SimpleImmutableEntry` để giữ cả cặp có khóa hoặc giá trị `null`.

Đoạn helper có thể đặt trong một lớp:

~~~java
static <K, V> List<Map.Entry<K, V>> snapshotAllowingNulls(Map<K, V> source) {
    List<Map.Entry<K, V>> result = new ArrayList<>();
    for (Map.Entry<K, V> entry : source.entrySet()) {
        result.add(new AbstractMap.SimpleImmutableEntry<>(entry));
    }
    return result;
}
~~~

Cần import `Map`, `List`, `ArrayList` và `AbstractMap`. Helper tạo một danh sách sửa được, mỗi phần tử là một entry độc lập không hỗ trợ `setValue`.

`SimpleImmutableEntry` không gắn với khung nhìn của Map và không cho thay các tham chiếu khóa, giá trị qua `setValue`. Tên lớp không có nghĩa mọi đối tượng được khóa hoặc giá trị tham chiếu tới đều bất biến. [Java SE 17 — SimpleImmutableEntry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html).

Ví dụ nguồn:

~~~text
null  -> root
empty -> null
~~~

Bản sao có hai entry `null=root` và `empty=null`. Sau khi Map đổi `empty` thành `filled`, entry bản sao vẫn giữ tham chiếu giá trị `null` đã được chép trước đó.

Nếu còn cần không cho sửa danh sách, có thể công bố một lớp bọc không sửa được quanh danh sách helper tạo ra, với điều kiện không tiếp tục để nơi khác sửa chính danh sách bên trong. Quyết định chấp nhận `null` nằm ở kiểu entry, cách tạo danh sách và dữ liệu đầu vào; không thể suy ra chỉ từ chữ “bản sao”.

## 7. Thứ tự của danh sách đến từ đâu?

Danh sách có chỉ số, nhưng việc chuyển đổi không tự tạo ra một thứ tự nghiệp vụ mới. Nó thu các phần tử theo thứ tự duyệt mà nguồn cung cấp.

### 7.1. LinkedHashMap: ví dụ có thứ tự chèn rõ ràng

`new LinkedHashMap<>()` mặc định giữ thứ tự chèn. Khi đưa `B` rồi `A` rồi `C` vào, các danh sách minh họa bắt đầu theo thứ tự ấy. Thay giá trị của khóa đã có bằng `put` không đưa khóa đó xuống cuối trong chế độ thứ tự chèn. [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

Đó là lý do chương trình dùng `LinkedHashMap` để có stdout dễ đối chiếu, thay vì in một thứ tự bất kỳ rồi gọi nó là chuẩn.

`LinkedHashMap` cũng có chế độ thứ tự truy cập được chọn bằng constructor khác. Trong chế độ ấy, một số thao tác đọc hoặc cập nhật có thể ảnh hưởng thứ tự. Không nên nói chung rằng mọi `LinkedHashMap` luôn dùng thứ tự chèn.

### 7.2. TreeMap: thứ tự theo khóa

`TreeMap` giữ khóa theo thứ tự tự nhiên hoặc comparator được cung cấp. Danh sách khóa lấy từ một `TreeMap<String, ...>` với thứ tự tự nhiên sẽ theo thứ tự chuỗi, không theo thời điểm chèn. [Java SE 17 — TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

Một `TreeMap` được tạo từ các khóa `B`, `A`, `C` sẽ cho danh sách khóa `[A, B, C]` khi dùng thứ tự tự nhiên của các chuỗi đó.

### 7.3. HashMap và các Map không cam kết thứ tự

Không được dựa vào thứ tự chèn, thứ tự tăng dần hoặc kết quả đã in một lần của `HashMap` như một hợp đồng. Tạo `ArrayList` từ khung nhìn giữ thứ tự quan sát trong lần duyệt đó; nó không bổ sung một cam kết cho những lần chuyển đổi khác.

Nếu cần thứ tự để xuất báo cáo, kiểm thử, phân trang hay hiển thị ổn định, hãy chọn nguồn có hợp đồng thứ tự phù hợp hoặc sắp xếp kết quả bằng tiêu chí rõ ràng.

Cũng đừng dùng `Map.of` để tạo dữ liệu rồi mặc nhiên kỳ vọng danh sách giữ đúng thứ tự đối số của lời gọi. Các factory đó không phải cách yêu cầu thứ tự chèn.

## 8. Sắp xếp cặp trước khi tách khóa hoặc giá trị

Để xếp điểm giảm dần, nếu bằng điểm thì mã tăng dần:

~~~java
List<Map.Entry<String, Integer>> sorted = scores.entrySet().stream()
        .map(Map.Entry::copyOf)
        .sorted(Map.Entry.<String, Integer>comparingByValue(Comparator.reverseOrder())
                .thenComparing(Map.Entry.<String, Integer>comparingByKey()))
        .toList();
~~~

Đoạn minh họa giả định khóa và điểm không `null`. `Comparator.reverseOrder()` đảo thứ tự của điểm; `thenComparing` bổ sung quy tắc theo mã khi điểm bằng nhau. [Java SE 17 — Comparator.thenComparing](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html#thenComparing(java.util.Comparator)).

Với nguồn `C=20`, `B=20`, `A=10`, kết quả là:

~~~text
[B=20, C=20, A=10]
~~~

Điểm không bị tách khỏi mã trong quá trình sắp xếp. Nếu cần danh sách mã theo đúng thứ hạng ấy, lấy khóa sau khi đã có thứ tự cặp:

~~~java
List<String> rankedKeys = sorted.stream()
        .map(Map.Entry::getKey)
        .toList();
~~~

Danh sách kết quả là `[B, C, A]`. Nếu chỉ cần danh sách điểm theo thứ hạng, dùng `Map.Entry::getValue` ở bước cuối.

Tiêu chí phụ có ích khi nhiều cặp có cùng điểm. Sắp xếp chỉ theo điểm có thể giữ một thứ tự gặp ban đầu giữa các cặp bằng điểm, nhưng nếu nguồn không có thứ tự được cam kết thì đó không tạo ra thứ tự ổn định cho mọi lần chạy. Thêm mã làm tiêu chí phụ diễn tả yêu cầu rõ ràng hơn.

Nếu có `null`, cần quyết định `null` đứng đầu hay cuối trước khi chọn comparator. Ví dụ có thể truyền một comparator xử lý `null` cho khóa hoặc giá trị. Nhưng bước `Map.Entry.copyOf` vẫn không chấp nhận `null`, nên phải chọn cách tạo entry phù hợp trước; comparator xử lý `null` không sửa được lỗi đã xảy ra ở giai đoạn sao chép entry.

### Không sắp xếp hai danh sách độc lập rồi ghép theo chỉ số

Từ `B=20`, `A=10`, `C=20`, nếu chỉ sắp xếp danh sách khóa thành `[A, B, C]` rồi ghép với danh sách giá trị cũ `[20, 10, 20]`, ta tạo `A=20` và `B=10`, sai dữ liệu gốc.

Ngay cả khi hai lần lấy danh sách lúc đầu có thể khớp trong một nguồn ổn định có thứ tự tương ứng, các bước sửa, lọc hoặc thay đổi Map giữa hai lần lấy vẫn dễ phá quan hệ. Nếu nhiệm vụ cần cặp, dùng cặp làm đơn vị xử lý.

## 9. Lọc và chuyển thành dữ liệu đầu ra

Có thể chỉ lấy những cặp có điểm từ `20` trở lên:

~~~java
List<Map.Entry<String, Integer>> qualified = scores.entrySet().stream()
        .filter(entry -> entry.getValue() >= 20)
        .map(Map.Entry::copyOf)
        .toList();
~~~

Đây là đoạn minh họa với các điểm `Integer` khác `null`. Nếu giá trị có thể `null`, điều kiện phải xử lý điều đó trước khi so sánh số.

Việc lọc tạo một kết quả mới; nó không xóa các ánh xạ không đạt từ Map. Nếu muốn sửa Map, đó là một yêu cầu khác và cần thao tác đúng trên cấu trúc nguồn.

Đôi khi dữ liệu đầu ra nên có tên nghiệp vụ thay vì `Map.Entry`. Ví dụ một kiểu `record ScoreRow(String code, Integer score)` có thể thể hiện rõ cột mã và điểm trong một bảng hiển thị. Khi chuyển thành record, đọc khóa và giá trị trong cùng một lần duyệt rồi tạo một dòng độc lập.

Dù dùng entry hay record, việc đổi kiểu bao ngoài vẫn chỉ chép các tham chiếu nếu trường bên trong là đối tượng. Nó không tự tạo bản sao sâu của hồ sơ, địa chỉ hoặc danh sách con trong giá trị.

Một danh sách mới cũng không phải một bộ đồng bộ trở lại Map. Chỉnh dòng trong danh sách làm việc không tự biết phải cập nhật khóa nào, có cho thêm khóa không, và xử lý thế nào nếu Map đã thay đổi kể từ lúc lấy dữ liệu. Những quy tắc ấy cần được thiết kế tường minh ở thời điểm ghi kết quả.

## 10. Quyền sửa danh sách và quyền sửa phần tử là hai tầng

| Cách tạo | Cấu trúc danh sách | Các entry được giữ |
| --- | --- | --- |
| `new ArrayList<>(map.entrySet())` | Có thể sửa | Chỉ chép các tham chiếu entry từ nguồn; không được xem là bản sao entry độc lập |
| `map.entrySet().stream().toList()` | Không cho sửa danh sách | Vẫn chưa có bước tạo entry độc lập |
| `stream().map(Map.Entry::copyOf).toList()` | Không cho sửa danh sách | Entry độc lập, không cho `setValue`, không chấp nhận phần khóa/giá trị null |
| `stream().map(Map.Entry::copyOf).collect(toCollection(ArrayList::new))` | Có thể sửa | Entry độc lập nhưng vẫn không cho `setValue` |
| Helper dùng `SimpleImmutableEntry` và `ArrayList` | Có thể sửa | Entry độc lập, không cho `setValue`, có thể biểu diễn phần khóa/giá trị null |

`Stream.toList()` từ Java 16 trả về danh sách không cho sửa và giữ thứ tự gặp nếu stream có thứ tự. Điều đó không làm các đối tượng phần tử tự bất biến. [Java SE 17 — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()).

Nếu cần chắc chắn một `ArrayList` sửa được, dùng constructor hoặc `Collectors.toCollection(ArrayList::new)`. Không coi `Collectors.toList()` như hợp đồng bắt buộc phải trả `ArrayList` sửa được: tài liệu không bảo đảm kiểu triển khai hay quyền sửa của kết quả ấy. [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)).

Hãy kiểm tra hai câu lệnh khác nhau:

~~~java
entries.remove(0);
entries.get(0).setValue(500);
~~~

Lệnh đầu yêu cầu quyền sửa danh sách. Lệnh sau yêu cầu quyền sửa đối tượng entry đang ở vị trí `0`. Một trong hai chạy được không chứng minh lệnh kia chạy được; và entry độc lập sửa được cũng không có nghĩa nó ghi về Map.

## 11. Bản sao cặp vẫn có thể dùng chung đối tượng giá trị

Xét giá trị là `StringBuilder`:

~~~java
StringBuilder item = new StringBuilder("seed");
Map<String, StringBuilder> source = new LinkedHashMap<>();
source.put("item", item);

List<Map.Entry<String, StringBuilder>> snapshot = source.entrySet().stream()
        .map(Map.Entry::copyOf)
        .toList();
~~~

Entry đã tách khỏi Map. Tuy nhiên, giá trị nó giữ vẫn là tham chiếu tới `item`.

Sau `item.append("!")`, đọc giá trị trong entry bản sao sẽ thấy `seed!`. Không có tham chiếu giá trị nào bị thay ở cấp entry; chính đối tượng được tham chiếu đã đổi trạng thái.

Nếu sau đó gọi:

~~~java
source.put("item", new StringBuilder("replacement"));
~~~

Map trỏ sang đối tượng mới. Entry bản sao vẫn giữ đối tượng cũ `seed!`. Đây là khác biệt giữa **thay ánh xạ tới đối tượng khác** và **sửa chính đối tượng đang được dùng chung**.

Bản sao sâu đòi hỏi quy tắc cho từng kiểu giá trị. Với một mô hình nghiệp vụ, có thể tạo đối tượng dữ liệu bất biến riêng hoặc chép từng trường cần giữ. Không thể yêu cầu một phương thức chuyển Map thành List tổng quát tự hiểu mọi quan hệ đối tượng và tạo đúng bản sao sâu cho chúng.

## 12. Khi Map có thể bị sửa đồng thời

Một phép chuyển đổi phải duyệt nguồn. `new ArrayList<>(map.values())` và stream sao chép entry không tự khóa toàn bộ Map hoặc biến nhiều lần đọc thành một ảnh chụp nguyên tử.

Với một Map thông thường được bảo vệ bằng khóa, toàn bộ quá trình tạo danh sách cần tuân thủ cùng giao thức khóa với các nơi sửa Map. Riêng `Collections.synchronizedMap` yêu cầu đồng bộ trên chính Map bọc khi duyệt các khung nhìn; không thay bằng việc tự khóa `keySet` hoặc `entrySet`. [Java SE 17 — Collections.synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

Với `ConcurrentHashMap`, việc duyệt có hợp đồng phù hợp truy cập đồng thời nhưng không mặc nhiên cho một ảnh chụp toàn bộ tại một thời điểm duy nhất. Danh sách cuối cùng có thể là tập các quan sát trong thời gian duyệt. [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Hai tính chất phải được đánh giá riêng:

- Sau khi tạo, entry bản sao không còn liên kết với các thay đổi ánh xạ của Map.
- Trong lúc tạo, các cặp được thu thập có thuộc cùng một trạng thái nhất quán toàn cục hay không.

`Map.Entry.copyOf` giải quyết tính chất thứ nhất ở cấp cặp tham chiếu; nó không tự cung cấp tính chất thứ hai. Nếu nghiệp vụ cần một báo cáo nhất quán giữa nhiều khóa, chọn chiến lược phối hợp phù hợp thay vì chỉ đổi collection đầu ra.

Chương trình của bài giữ nguồn ổn định khi tạo từng danh sách và chỉ thay Map sau khi các bước tương ứng hoàn tất.

## 13. Chương trình minh chứng đầy đủ

Lưu mã thành **MapListsDemo.java**. Các API được dùng tương thích Java 17; `Map.Entry.copyOf` là phần cần Java 17 trong ví dụ.

Hàm `rejects` xác nhận loại ngoại lệ dự kiến. Helper `snapshotAllowingNulls` tạo bản sao entry độc lập trong lúc duyệt, giữ được khóa hoặc giá trị `null`. Lần cập nhật bằng `entry.setValue` được thực hiện ngay trong vòng duyệt, không lưu entry từ khung nhìn để dùng sau.

~~~java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MapListsDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " did not fail");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static <K, V> List<Map.Entry<K, V>> snapshotAllowingNulls(Map<K, V> source) {
        List<Map.Entry<K, V>> result = new ArrayList<>();
        for (Map.Entry<K, V> entry : source.entrySet()) {
            result.add(new AbstractMap.SimpleImmutableEntry<>(entry));
        }
        return result;
    }

    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("B", 20);
        scores.put("A", 10);
        scores.put("C", 20);

        Set<String> keyView = scores.keySet();
        Collection<Integer> valueView = scores.values();
        List<String> keys = new ArrayList<>(keyView);
        List<Integer> values = new ArrayList<>(valueView);
        List<Map.Entry<String, Integer>> entries = scores.entrySet().stream()
                .map(Map.Entry::copyOf)
                .collect(Collectors.toCollection(ArrayList::new));
        System.out.println("keys=" + keys);
        System.out.println("values=" + values);
        System.out.println("entries=" + entries);

        scores.put("A", 99);
        scores.put("D", 30);
        System.out.println("map-after-put=" + scores);
        System.out.println("key-view=" + keyView);
        System.out.println("value-view=" + valueView);
        System.out.println("copied-keys=" + keys);
        System.out.println("copied-values=" + values);
        System.out.println("snapshot-entries=" + entries);

        keys.remove("B");
        values.add(777);
        entries.remove(0);
        System.out.println("edited-lists=" + keys + " / " + values + " / " + entries);
        System.out.println("map-after-list-edits=" + scores);
        rejects("snapshot-setValue", UnsupportedOperationException.class,
                () -> entries.get(0).setValue(500));

        for (Map.Entry<String, Integer> entry : scores.entrySet()) {
            if (entry.getKey().equals("B")) {
                System.out.println("iterator-setValue-old=" + entry.setValue(25));
            }
        }
        System.out.println("map-after-entry-update=" + scores);
        keyView.remove("D");
        System.out.println("map-after-view-remove=" + scores);

        List<Map.Entry<String, Integer>> frozen = scores.entrySet().stream()
                .map(Map.Entry::copyOf)
                .toList();
        rejects("stream-list-add", UnsupportedOperationException.class,
                () -> frozen.add(Map.entry("X", 1)));
        System.out.println("frozen=" + frozen);

        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(frozen);
        sorted.sort(Map.Entry.<String, Integer>comparingByValue(Comparator.reverseOrder())
                .thenComparing(Map.Entry.<String, Integer>comparingByKey()));
        System.out.println("sorted=" + sorted);
        System.out.println("map-order=" + new ArrayList<>(scores.keySet()));

        Map<String, Integer> tieMap = new LinkedHashMap<>();
        tieMap.put("C", 20);
        tieMap.put("B", 20);
        tieMap.put("A", 10);
        List<Map.Entry<String, Integer>> tieSorted = tieMap.entrySet().stream()
                .map(Map.Entry::copyOf)
                .sorted(Map.Entry.<String, Integer>comparingByValue(Comparator.reverseOrder())
                        .thenComparing(Map.Entry.<String, Integer>comparingByKey()))
                .toList();
        System.out.println("tie-sorted=" + tieSorted);

        Map<String, Integer> tree = new TreeMap<>(scores);
        System.out.println("tree-keys=" + new ArrayList<>(tree.keySet()));

        Map<String, String> nullable = new LinkedHashMap<>();
        nullable.put(null, "root");
        nullable.put("empty", null);
        List<Map.Entry<String, String>> nullableEntries = snapshotAllowingNulls(nullable);
        System.out.println("nullable-keys=" + new ArrayList<>(nullable.keySet()));
        System.out.println("nullable-values=" + new ArrayList<>(nullable.values()));
        System.out.println("nullable-entries=" + nullableEntries);
        rejects("copyOf-null-entry-part", NullPointerException.class,
                () -> nullable.entrySet().stream().map(Map.Entry::copyOf).toList());
        rejects("nullable-entry-setValue", UnsupportedOperationException.class,
                () -> nullableEntries.get(0).setValue("changed"));
        nullable.put("empty", "filled");
        System.out.println("nullable-map=" + nullable);
        System.out.println("nullable-snapshot=" + nullableEntries);

        AbstractMap.SimpleEntry<String, Integer> local =
                new AbstractMap.SimpleEntry<>("local", 1);
        local.setValue(2);
        System.out.println("detached-editable-entry=" + local);

        StringBuilder item = new StringBuilder("seed");
        Map<String, StringBuilder> objects = new LinkedHashMap<>();
        objects.put("item", item);
        List<Map.Entry<String, StringBuilder>> shallow = objects.entrySet().stream()
                .map(Map.Entry::copyOf)
                .toList();
        item.append("!");
        System.out.println("shared-value-object=" + shallow.get(0).getValue());
        objects.put("item", new StringBuilder("replacement"));
        System.out.println("rebound-map-value=" + objects.get("item"));
        System.out.println("snapshot-old-reference=" + shallow.get(0).getValue());
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 MapListsDemo.java
java MapListsDemo
~~~

Stdout chính xác:

~~~text
keys=[B, A, C]
values=[20, 10, 20]
entries=[B=20, A=10, C=20]
map-after-put={B=20, A=99, C=20, D=30}
key-view=[B, A, C, D]
value-view=[20, 99, 20, 30]
copied-keys=[B, A, C]
copied-values=[20, 10, 20]
snapshot-entries=[B=20, A=10, C=20]
edited-lists=[A, C] / [20, 10, 20, 777] / [A=10, C=20]
map-after-list-edits={B=20, A=99, C=20, D=30}
snapshot-setValue -> UnsupportedOperationException
iterator-setValue-old=20
map-after-entry-update={B=25, A=99, C=20, D=30}
map-after-view-remove={B=25, A=99, C=20}
stream-list-add -> UnsupportedOperationException
frozen=[B=25, A=99, C=20]
sorted=[A=99, B=25, C=20]
map-order=[B, A, C]
tie-sorted=[B=20, C=20, A=10]
tree-keys=[A, B, C]
nullable-keys=[null, empty]
nullable-values=[root, null]
nullable-entries=[null=root, empty=null]
copyOf-null-entry-part -> NullPointerException
nullable-entry-setValue -> UnsupportedOperationException
nullable-map={null=root, empty=filled}
nullable-snapshot=[null=root, empty=null]
detached-editable-entry=local=2
shared-value-object=seed!
rebound-map-value=replacement
snapshot-old-reference=seed!
~~~

Mã đã biên dịch bằng `--release 17` và chạy trên JDK 24.0.2. Đây là kiểm tra tương thích mức API/ngôn ngữ Java 17 và kết quả chạy trên JVM đã nêu; không phải tuyên bố đã chạy bằng JVM 17.

Những điểm cần đối chiếu trong stdout:

- Ba dòng đầu chứa cùng ba ánh xạ nhìn dưới ba dạng, trong đó danh sách giá trị giữ cả hai lần `20`.
- Sau `put`, các khung nhìn thấy dữ liệu mới nhưng danh sách khóa, giá trị và bản sao entry đã tạo vẫn giữ dữ liệu của lần chép trước.
- `edited-lists` thay đổi mà `map-after-list-edits` không đổi; `snapshot-setValue` bị từ chối vì entry bản sao không hỗ trợ thay giá trị.
- `iterator-setValue-old` trả về điểm cũ và `map-after-entry-update` thấy điểm mới vì thao tác diễn ra qua entry đang được duyệt.
- `map-after-view-remove` minh họa xóa trực tiếp qua khung nhìn, khác với xóa trên danh sách đã chép.
- `sorted` và `tie-sorted` giữ khóa đi với điểm; `map-order` cho thấy sắp xếp danh sách không sắp xếp lại Map.
- Các dòng `nullable` phân biệt bản sao cho phép phần dữ liệu null với `Map.Entry.copyOf` không chấp nhận chúng.
- Ba dòng cuối phân biệt sửa đối tượng giá trị dùng chung với thay ánh xạ Map sang một đối tượng khác.

## 14. Thực hành có đáp án

### Bài 1 — Chọn kiểu danh sách

Một hàm chỉ cần kiểm tra những mã đang có; một hàm khác cần xếp hạng điểm và hiện mã đi kèm. Mỗi hàm nên lấy khung nhìn nào để tạo danh sách?

**Đáp án:** Hàm đầu lấy `keySet` và tạo `List<K>`. Hàm xếp hạng lấy `entrySet`, tạo các entry độc lập rồi sắp xếp cặp trước khi trình bày. Chỉ lấy `values` sẽ đánh mất quan hệ giữa mã và điểm.

### Bài 2 — Giá trị trùng có bị mất không?

Map có `A=10`, `B=10`, `C=20`. `new ArrayList<>(map.values())` có bao nhiêu phần tử? Nếu thay bằng một Set thì điều gì thay đổi?

**Đáp án:** Danh sách có ba phần tử, gồm hai lần `10`. Set có thể gộp hai giá trị bằng nhau và làm mất số lần xuất hiện. Việc loại trùng cần là yêu cầu rõ ràng, không phải một bước chuyển đổi mặc định.

### Bài 3 — Xóa trên khung nhìn và danh sách

Sau `List<String> keys = new ArrayList<>(map.keySet())`, gọi `keys.remove("A")` có xóa `A` của Map không? Còn `map.keySet().remove("A")` khi Map hỗ trợ xóa?

**Đáp án:** Lệnh đầu chỉ sửa danh sách độc lập. Lệnh sau thao tác trên khung nhìn và xóa ánh xạ của Map. Hai biến có thể chứa cùng các khóa ban đầu nhưng mang quan hệ khác với nguồn.

### Bài 4 — Danh sách entry mới đã đủ làm bản sao chưa?

Vì sao `new ArrayList<>(map.entrySet())` chưa đủ để cam kết các cặp giữ nguyên khi Map thay đổi?

**Đáp án:** Constructor chỉ tạo danh sách và chép tham chiếu phần tử, không tạo entry độc lập. Entry lấy từ khung nhìn còn có giới hạn sử dụng theo hợp đồng duyệt. Dùng bước sao chép entry trong lúc duyệt, chẳng hạn `Map.Entry.copyOf` với dữ liệu không null hoặc `SimpleImmutableEntry` khi cần giữ phần khóa/giá trị null.

### Bài 5 — Danh sách sửa được, entry không sửa được

Một danh sách được tạo bằng `map(Map.Entry::copyOf).collect(Collectors.toCollection(ArrayList::new))`. Vì sao `remove(0)` có thể chạy mà `get(0).setValue(...)` lại ném lỗi?

**Đáp án:** Quyền sửa danh sách thuộc `ArrayList`. Quyền sửa giá trị entry thuộc đối tượng do `copyOf` cung cấp, vốn không cho `setValue`. Hai tầng quyền thay đổi độc lập với nhau.

### Bài 6 — Dữ liệu null cần giữ nguyên

Map cho phép khóa null và giá trị null. Không được bỏ hoặc đổi dữ liệu. Có thể dùng thẳng `Map.Entry.copyOf` cho mọi entry không?

**Đáp án:** Không, phương thức đó từ chối cả khóa hoặc giá trị null. Tạo từng `new AbstractMap.SimpleImmutableEntry<>(entry)` khi duyệt để giữ dữ liệu và tách entry khỏi Map. Sau đó chọn quyền sửa của danh sách theo yêu cầu riêng.

### Bài 7 — Giữ quan hệ khi sắp xếp

Nguồn theo thứ tự chèn là `C=20`, `B=20`, `A=10`. Cần điểm giảm dần và mã tăng dần khi bằng điểm. Kết quả nào đúng và vì sao không chỉ sắp danh sách khóa?

**Đáp án:** `[B=20, C=20, A=10]`. Sắp xếp cả cặp theo điểm rồi theo mã giữ quan hệ dữ liệu. Sắp riêng khóa rồi ghép với các giá trị chưa được sắp tương ứng có thể tạo cặp sai. Tiêu chí phụ theo mã cũng làm thứ tự giữa hai điểm `20` trở nên rõ ràng.

### Bài 8 — Bản sao và đối tượng dùng chung

Giá trị Map là một `StringBuilder`. Sau khi tạo entry bằng `copyOf`, sửa `StringBuilder` ban đầu có hiện trong bản sao không? Nếu dùng `put` để thay bằng một `StringBuilder` mới thì sao?

**Đáp án:** Sửa đối tượng ban đầu được nhìn thấy qua tham chiếu giá trị đã chép. Thay ánh xạ bằng `put` không đổi tham chiếu mà entry độc lập đang giữ. Muốn tách cả trạng thái bên trong, cần quy tắc sao chép đối tượng hoặc kiểu giá trị bất biến phù hợp.

## 15. Chọn kết quả theo hợp đồng đầu ra

Nếu cần mã, lấy khóa; nếu cần dữ liệu tổng hợp không cần quan hệ mã, lấy giá trị; nếu cần từng dòng khóa–giá trị, giữ entry hoặc tạo đối tượng dòng rõ nghĩa. Sau đó xác định thứ tự và quyền sửa của kết quả.

Khi cần giữ dữ liệu để dùng về sau, hãy tạo entry độc lập trong quá trình duyệt, xử lý null theo một chính sách đã chọn, và nhớ rằng khóa hoặc giá trị là đối tượng sửa được vẫn có thể được dùng chung. Một bản sao danh sách chỉ bảo đảm cấu trúc danh sách mới; mức tách dữ liệu phải đến từ cách sao chép phần tử.

Cách suy luận này giúp chuyển Map sang danh sách để hiển thị, sắp xếp, lọc hoặc truyền qua API mà vẫn giữ đúng quan hệ và hiểu rõ nơi nào có thể bị thay đổi.
