# Autoboxing, unboxing và chi phí của kiểu bao

Trong Java Collections Framework, đoạn mã sau trông như đang lưu trực tiếp các số nguyên:

```java
List<Integer> scores = new ArrayList<>();
scores.add(10);
int first = scores.get(0);
```

Nhưng kiểu phần tử của danh sách là `Integer`, còn literal `10` và biến `first` có kiểu `int`. Java cho phép viết gọn nhờ chuyển đổi tự động giữa kiểu nguyên thủy và kiểu bao.

Sự tiện lợi này không xóa khác biệt giữa giá trị nguyên thủy và tham chiếu đối tượng. Những khác biệt đó thể hiện ở khả năng nhận `null`, phép so sánh, lựa chọn overload, dung lượng dữ liệu và chi phí xử lý.

Bài này dùng Java 17, tập trung vào cách boxing và unboxing xuất hiện khi dùng collection. Chương trình đầy đủ có lệnh biên dịch và kết quả chuẩn ở phần thực nghiệm. Các đoạn ngắn khác chỉ minh họa từng điểm; đoạn được ghi rõ “không biên dịch” là ví dụ lỗi có chủ ý.

## 1. Vì sao collection số cần kiểu bao?

### 1.1. Kiểu nguyên thủy và kiểu tham chiếu

`int` biểu diễn một giá trị số nguyên. `Integer` là lớp bao biểu diễn một giá trị `int` trong một đối tượng.

Với generic của Java 17, tham số kiểu phải là kiểu tham chiếu. Do đó:

```java
List<Integer> scores = new ArrayList<>();
```

là hợp lệ, còn khai báo dưới đây không biên dịch:

```java
List<int> scores;
```

Collection như `ArrayList<Integer>` tổ chức các phần tử dưới dạng tham chiếu đến `Integer`, không phải một mảng chuyên biệt chứa trực tiếp các giá trị `int`.

### 1.2. Các cặp kiểu thường gặp

| Kiểu nguyên thủy | Kiểu bao |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

Tên lớp không phải lúc nào cũng chỉ là viết hoa ký tự đầu: `int` đi với `Integer`, `char` đi với `Character`.

### 1.3. Vì sao không chỉ dùng mảng nguyên thủy?

`int[]` phù hợp với nhiều bài toán số học, nhưng không có cùng API và mô hình tổ chức dữ liệu như `List<Integer>`, `Set<Integer>` hay `Map<String, Integer>`.

Kiểu bao giúp các giá trị số tham gia một framework chung: có thể làm phần tử, khóa, giá trị và được truyền qua các API nhận đối tượng. Lợi ích là tính tương tác cùng khả năng diễn đạt dữ liệu; chi phí là các lớp chuyển đổi và biểu diễn đối tượng cần được hiểu rõ.

## 2. Boxing và autoboxing

**Boxing** là chuyển từ kiểu nguyên thủy sang kiểu bao tương ứng. **Autoboxing** là cách gọi thông dụng khi Java thực hiện chuyển đổi này tự động trong một ngữ cảnh cho phép.

Ví dụ:

```java
int raw = 42;
Integer boxed = raw;
```

Có thể hình dung cách viết tương đương về giá trị:

```java
Integer boxed = Integer.valueOf(raw);
```

Đây là cách diễn đạt để hiểu chuyển đổi; hợp đồng ngôn ngữ không nên được thay bằng một giả định rằng mọi compiler phải sinh đúng một chuỗi bytecode cố định.

### 2.1. Khi thêm số vào collection

Đoạn minh họa:

```java
List<Integer> values = new ArrayList<>();
values.add(42);
```

Tham số phần tử cần `Integer`, còn `42` có kiểu `int`; boxing xảy ra tại ranh giới này.

Với map:

```java
Map<Integer, Integer> counts = new HashMap<>();
counts.put(7, 1);
```

Cả khóa và giá trị đều được biểu diễn bằng kiểu bao. Không nên nhìn hai literal nguyên thủy rồi kết luận map đang lưu trực tiếp hai giá trị `int` trong cấu trúc chuyên biệt.

### 2.2. Boxing không đồng nghĩa luôn cấp phát một đối tượng mới

Một giá trị có thể dùng đối tượng đã được lưu đệm. Trong một số hoàn cảnh, JVM cũng có thể tối ưu các đối tượng trung gian nếu vẫn giữ đúng hành vi quan sát được.

Vì vậy, phát biểu “mỗi lần viết một số vào `List<Integer>` chắc chắn tạo một đối tượng mới” là quá mạnh. Cần phân biệt:

- Có chuyển đổi boxing theo ngữ nghĩa.
- Có lời gọi hoặc cơ chế tạo giá trị bao.
- Có đối tượng mới thực sự được cấp phát khi chạy.
- Đối tượng đó còn tồn tại bao lâu.

Các quy tắc chuyển đổi được nêu trong [JLS 17, mục Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7).

## 3. Unboxing: từ tham chiếu về giá trị nguyên thủy

**Unboxing** lấy giá trị nguyên thủy từ kiểu bao tương ứng.

Ví dụ:

```java
Integer boxed = Integer.valueOf(42);
int raw = boxed;
```

Có thể hiểu tương tự:

```java
int raw = boxed.intValue();
```

Khi đọc collection:

```java
int score = scores.get(0);
```

`get` trả `Integer`; phép gán sang `int` yêu cầu unboxing.

### 3.1. Unboxing trong vòng lặp

Đoạn minh họa:

```java
int sum = 0;
for (int value : values) {
    sum += value;
}
```

Nếu `values` là `List<Integer>`, mỗi phần tử được đọc dưới dạng tham chiếu rồi được dùng như `int`.

Đổi biến vòng lặp thành `Integer` không tự loại bỏ unboxing nếu thân vòng lặp vẫn làm số học:

```java
for (Integer value : values) {
    sum += value;
}
```

Ở đây, việc dùng `value` trong phép cộng vẫn yêu cầu giá trị nguyên thủy.

### 3.2. Unboxing không tạo một wrapper mới

Unboxing đọc giá trị từ wrapper; bản thân chuyển đổi này không phải bước cấp phát wrapper.

Chi phí thực tế có thể gồm truy cập tham chiếu, lấy giá trị và kiểm tra điều kiện cần thiết. JVM có thể nội tuyến hoặc tối ưu một số bước. Không nên gộp toàn bộ chi phí của một đoạn mã số học thành “chi phí unboxing” nếu đoạn đó còn có cấp phát, tra cứu collection hoặc thuật toán khác.

### 3.3. Có thể unbox rồi mở rộng kiểu nguyên thủy

Ví dụ:

```java
Integer boxed = 42;
long total = boxed;
```

Trường hợp này có thể unbox `Integer` thành `int`, rồi mở rộng sang `long`.

Điều đó khác với tự chuyển từ wrapper này sang wrapper khác. `Integer` không tự biến thành `Long` chỉ vì hai lớp đều biểu diễn số.

## 4. null: lỗi quan trọng nhất khi unboxing

### 4.1. Wrapper có thể là null, primitive thì không

Một biến `Integer` có thể không trỏ tới đối tượng nào:

```java
Integer count = null;
int primitive = count;
```

Lời gán thứ hai ném `NullPointerException`. Không tồn tại quy tắc tự chuyển `null` thành 0.

Điều tương tự áp dụng cho các cặp khác, ví dụ `Boolean` sang `boolean`. Quy tắc được nêu trực tiếp trong [JLS 17, mục Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8).

### 4.2. Map.get có thể trả null

Với `Map<String, Integer>`:

```java
int count = counts.get("missing");
```

có thể lỗi tại bước unboxing nếu không có ánh xạ hoặc nếu map cho phép giá trị `null` và khóa đang gắn với `null`.

Nên tách bước đọc và chính sách:

```java
Integer result = counts.get("missing");
int count = result == null ? 0 : result;
```

Ví dụ trên chủ động coi cả thiếu giá trị và giá trị `null` là 0. Đây là quyết định nghiệp vụ, không phải quy tắc đúng cho mọi chương trình.

Nếu cần phân biệt “chưa có khóa” với “khóa có nhưng chưa biết số lượng”, phải giữ sự phân biệt đó bằng dữ liệu hoặc kiểm tra bổ sung.

### 4.3. getOrDefault không thay mọi null bằng giá trị mặc định

Đoạn minh họa:

```java
Map<String, Integer> counts = new HashMap<>();
counts.put("unknown", null);

int count = counts.getOrDefault("unknown", 0);
```

Khóa `"unknown"` đã có ánh xạ với `null`, nên `getOrDefault` trả giá trị đang gắn với khóa. Gán kết quả sang `int` tiếp tục gây lỗi unboxing.

Đừng dùng tên “default” để suy ra nó là thao tác thay mọi `null`. Xem [Map.getOrDefault trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#getOrDefault(java.lang.Object,V)).

### 4.4. Boolean trong điều kiện

Đoạn minh họa:

```java
Boolean enabled = settings.get("enabled");
if (enabled) {
    startFeature();
}
```

Điều kiện `if` cần `boolean`; nếu `enabled` là `null`, có lỗi unboxing.

Nếu chính sách thực sự là “chỉ bật khi rõ ràng là true”, có thể dùng `Boolean.TRUE.equals(enabled)`. Cách đó cố ý coi `null` như chưa bật; không nên áp dụng khi thiếu cấu hình phải là lỗi cần báo.

### 4.5. Ternary có thể unbox trước khi gán sang wrapper

Đoạn minh họa:

```java
Integer nullable = null;
boolean useNullable = true;
Integer chosen = useNullable ? nullable : 0;
```

Mặc dù `chosen` là `Integer`, hai nhánh của toán tử điều kiện có kiểu khác nhau: một nhánh là `Integer`, một nhánh là `int`. Quy tắc của biểu thức số có thể yêu cầu unboxing nhánh `nullable`, rồi mới boxing kết quả cho phép gán. Khi nhánh đó được chọn và giá trị là `null`, chương trình ném `NullPointerException`.

Muốn giữ kiểu tham chiếu và cho phép `null`, phải viết các nhánh phù hợp với ý định, chẳng hạn dùng giá trị mặc định đã có kiểu `Integer`, hoặc tách thành `if`–`else` rõ ràng.

Muốn thay `null` bằng 0, kiểm tra chính `nullable == null` trước khi unbox. Quy tắc xác định kiểu của `?:` nằm trong [JLS 17, Conditional Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25).

## 5. Kiểu bao bất biến và phép tăng, cộng

### 5.1. Integer không phải một ô số có thể sửa tại chỗ

Đoạn minh họa:

```java
Integer counter = 1000;
Integer previous = counter;
counter++;
```

Sau đó `previous` vẫn biểu diễn 1000, còn `counter` biểu diễn 1001.

Để hiểu, có thể tách ý nghĩa của phép tăng:

1. Lấy giá trị `int` từ `counter`.
2. Tính kết quả tăng.
3. Chuyển kết quả sang kiểu bao cần thiết.
4. Gán lại tham chiếu cho biến `counter`.

Phép tăng không sửa giá trị bên trong đối tượng mà `previous` đang giữ.

### 5.2. Biến cộng dồn kiểu bao tạo thêm ranh giới chuyển đổi

So sánh hai đoạn minh họa:

```java
Integer boxedSum = 0;
for (int value : values) {
    boxedSum += value;
}
```

và:

```java
int primitiveSum = 0;
for (int value : values) {
    primitiveSum += value;
}
```

Nếu `values` là `List<Integer>`, cả hai vẫn unbox phần tử đầu vào.

Đoạn đầu còn phải xử lý biến tổng dưới dạng wrapper: lấy giá trị hiện tại để cộng rồi biểu diễn kết quả lại thành `Integer`. Đoạn sau giữ tổng ở kiểu nguyên thủy và chỉ cần boxing khi thực sự đi qua API yêu cầu đối tượng.

Đây là lý do nên ưu tiên biến tính toán cục bộ kiểu nguyên thủy khi không cần ý nghĩa `null` hoặc một API bắt buộc wrapper. Không khẳng định số lượng đối tượng cấp phát chỉ từ số vòng lặp, vì cache và tối ưu JVM có thể tác động.

### 5.3. Wrapper không mở rộng miền số của primitive tương ứng

Phép cộng sau khi unbox `Integer` vẫn có quy tắc số học của `int`. Dùng `Integer` không tự chống tràn số.

Với tổng lớn, cần chọn kiểu phép tính phù hợp, chẳng hạn cộng dồn bằng `long`, hoặc kiểm tra tràn theo yêu cầu. Chỉ thay kiểu biến nhận ở cuối không luôn sửa được một phép tính đã tràn ở bước trước.

## 6. ==, equals và bộ nhớ đệm

### 6.1. Hai toán hạng wrapper có thể đang được so sánh tham chiếu

Đoạn minh họa:

```java
Integer a = 100;
Integer b = 100;
boolean sameReference = a == b;
```

Ở đây `==` so sánh tham chiếu vì cả hai toán hạng đều có kiểu `Integer`.

Với hai literal hằng 100, có bảo đảm dùng chung tham chiếu theo quy tắc boxing của những giá trị được quy định. Kết quả `true` không biến `==` thành phép so sánh giá trị tổng quát cho mọi wrapper.

### 6.2. Không dựa vào kết quả của giá trị ngoài vùng bảo đảm

`Integer.valueOf(int)` luôn lưu đệm các giá trị từ -128 đến 127 và có thể lưu đệm thêm. Vì vậy, không viết bài kiểm tra hay nghiệp vụ phụ thuộc kết quả `==` của hai wrapper có cùng giá trị 1000 là `false`.

Có hai lớp bảo đảm cần phân biệt:

- JLS quy định một số điều kiện dùng chung tham chiếu khi boxing các biểu thức hằng.
- API `Integer.valueOf` mô tả chính sách lưu đệm của phương thức.

Cả hai không cho phép dùng danh tính đối tượng làm thay thế cho so sánh giá trị. Xem [Integer.valueOf trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#valueOf(int)).

### 6.3. So sánh giá trị cùng kiểu

Nếu hai giá trị có kiểu `Integer` và muốn so sánh giá trị có xét `null`, có thể dùng:

```java
boolean sameValue = Objects.equals(a, b);
```

Hoặc gọi `a.equals(b)` khi đã bảo đảm `a` không `null`.

`Integer.equals` yêu cầu đối số là `Integer` có cùng giá trị, nên:

```java
Integer.valueOf(1).equals(Long.valueOf(1L))
```

là `false`. `Objects.equals` không tự chuẩn hóa mọi kiểu số về một kiểu chung.

### 6.4. Khi một phía là primitive

Đoạn minh họa:

```java
Integer boxed = 10;
boolean equal = boxed == 10;
```

Ở biểu thức số này, giá trị bao được unbox để so sánh. Nếu `boxed` là `null`, có thể ném `NullPointerException`.

Vì thế, thay một phía của phép so sánh từ `Integer` sang `int` có thể đổi cả loại phép so sánh lẫn khả năng phát sinh lỗi.

### 6.5. Không dùng wrapper làm khóa đồng bộ dựa vào danh tính

Các đối tượng bao có thể được chia sẻ và được thiết kế như giá trị. Dùng chúng làm đối tượng khóa hoặc dựa vào danh tính để đại diện quyền sở hữu tạo phụ thuộc không đúng với mục đích kiểu dữ liệu.

Chọn một cơ chế đồng bộ hoặc một đối tượng khóa có ý nghĩa rõ ràng thay vì tận dụng một giá trị số được boxing.

## 7. Overload: Java chọn phương thức trước khi chạy

### 7.1. Bẫy remove của `List<Integer>`

`List` có cả:

```java
E remove(int index);
boolean remove(Object value);
```

Đây là hai khai báo để đọc hợp đồng, không phải nội dung đặt trực tiếp vào `main`.

Với:

```java
List<Integer> values = new ArrayList<>(List.of(10, 20, 30));
values.remove(1);
```

đối số `1` có kiểu `int`, nên phương thức xóa theo chỉ số được chọn. Phần tử bị xóa là 20.

Muốn xóa giá trị 30:

```java
boolean removed = values.remove(Integer.valueOf(30));
```

Không viết `values.remove(30)` rồi kỳ vọng xóa số 30; đó là yêu cầu xóa chỉ số 30 và có thể vượt phạm vi.

### 7.2. Thay kiểu biến có thể đổi overload

Đoạn minh họa:

```java
int index = 1;
Integer value = 1;
```

Truyền `index` vào `remove` khác truyền `value`. Khi đọc mã, cần xem kiểu tại thời điểm biên dịch, không chỉ xem giá trị in ra đều là 1.

### 7.3. Mở rộng primitive không giống mở rộng rồi boxing tùy ý

Đoạn hợp lệ:

```java
List<Long> values = new ArrayList<>();
values.add(1L);
```

Đoạn dưới không biên dịch:

```java
List<Long> values = new ArrayList<>();
values.add(1);
```

Literal `1` là `int`; cơ chế chuyển đổi đối số không tự thực hiện chuỗi tùy ý `int → long → Long` để đáp ứng yêu cầu này.

Có thể dùng literal `1L`, chuyển biểu thức sang `long` trước khi boxing, hoặc gọi hàm tạo giá trị phù hợp. Đọc ngữ cảnh chuyển đổi thay vì coi autoboxing là một bộ chuyển đổi số vạn năng.

## 8. Khóa số trong Map và phần tử trong Set

### 8.1. Tra cứu bằng Object vẫn cần đúng kiểu giá trị

Với:

```java
Map<Integer, String> names = Map.of(1, "one");
```

`names.get(1)` có thể boxing đối số thành `Integer` phù hợp với khóa đang có.

Nhưng:

```java
names.get(1L);
```

truyền một `Long` qua tham số kiểu `Object`. Nó không tự biến thành `Integer` để phù hợp ý định tra cứu.

Với map trong ví dụ, không có khóa `Long` tương ứng; kết quả là `null`. Phép tra cứu biên dịch được vì chữ ký nhận `Object`, không phải vì hai kiểu số đã được thống nhất.

### 8.2. Cùng số học chưa chắc cùng equals

Một tập `Set<Number>` có thể chứa cả `Integer.valueOf(1)` và `Long.valueOf(1)`. Đối với bình đẳng của hai kiểu bao này, chúng không phải cùng một giá trị đối tượng.

Nếu miền nghiệp vụ cần coi các biểu diễn số khác nhau là tương đương, phải chuẩn hóa kiểu hoặc xây dựng quan hệ đối chiếu rõ ràng. Không dựa vào boxing để làm việc đó.

### 8.3. Chi phí tại mỗi lần tra cứu

Một lời gọi tra cứu bằng khóa primitive vào map dùng khóa wrapper có ranh giới boxing ở cấp mã nguồn. Tùy giá trị và JVM, đối tượng tạm có thể dùng cache hoặc được tối ưu.

Không kết luận chỉ nhìn lời gọi `get` rằng chắc chắn có một đối tượng mới tồn tại lâu dài. Nhưng cũng không bỏ qua chi phí này khi đường nóng thực hiện hàng triệu phép tra cứu và số liệu đo cho thấy nó đáng kể.

## 9. Chi phí của kiểu bao gồm những gì?

### 9.1. Biểu diễn dữ liệu

Có thể hình dung khác biệt giữa mảng primitive và danh sách wrapper:

```text
int[]:
    một đối tượng mảng chứa các giá trị int

ArrayList<Integer>:
    đối tượng ArrayList
        -> mảng lưu các tham chiếu
              -> các đối tượng Integer được tham chiếu
```

Đây là mô hình khái niệm về các thành phần biểu diễn, không phải sơ đồ byte chính xác cho mọi JVM.

`ArrayList` có sức chứa có thể lớn hơn số phần tử đang dùng. Ngoài đối tượng bao, còn phải tính cấu trúc list và vùng tham chiếu. `Integer[]` cũng là mảng tham chiếu đến wrapper; nó không giống `int[]`.

### 9.2. Bộ nhớ không có một tỉ lệ cố định cho mọi JVM

`int` có miền biểu diễn 32 bit, nhưng từ đó không thể kết luận chính xác một triệu `Integer` sẽ chiếm bao nhiêu byte trên mọi cấu hình.

Kích thước thực tế phụ thuộc:

- Header đối tượng và header mảng.
- Độ rộng tham chiếu.
- Căn chỉnh đối tượng.
- Sức chứa chưa dùng của collection.
- Số đối tượng wrapper thực sự khác nhau được tham chiếu.
- Đối tượng dùng chung từ cache hoặc từ nơi khác.
- Cách JVM tối ưu và bố trí bộ nhớ.

Hai vị trí cùng tham chiếu một `Integer` không có nghĩa tồn tại hai đối tượng bao riêng. Ngược lại, cùng một giá trị ngoài cache có thể được biểu diễn bằng nhiều đối tượng khác nhau. Phải phân biệt số phần tử, số giá trị khác nhau và số đối tượng khác nhau.

### 9.3. Cấp phát và thu gom rác

Nếu một phép tính tạo nhiều đối tượng bao không được giữ lâu, có thể tăng tốc độ cấp phát và lượng dữ liệu cần thu gom.

Nếu một collection giữ nhiều wrapper lâu dài, chúng có thể ảnh hưởng tập đối tượng sống và dung lượng heap. Hai vấn đề này khác nhau: cấp phát nhiều trong thời gian ngắn không giống giữ dữ liệu lớn lâu dài.

Không phải mọi đối tượng tạm đều còn tồn tại sau tối ưu. Tuy nhiên, đối tượng đã được đưa vào một cấu trúc có thể quan sát được không thể mặc nhiên coi là đã bị loại bỏ.

### 9.4. Truy cập dữ liệu và tính cục bộ

Với dữ liệu số lớn, đi qua các tham chiếu và đối tượng riêng có thể có đặc điểm truy cập bộ nhớ khác mảng primitive. Cách sử dụng bộ nhớ đệm CPU và lượng dữ liệu phải đọc có thể ảnh hưởng tổng thời gian.

Đây là lý do chi phí kiểu bao không chỉ là một lời gọi `intValue()`. Nó có thể nằm ở toàn bộ hình dạng dữ liệu.

### 9.5. Big-O không mô tả mọi chi phí

Một vòng lặp cộng `int[]` và một vòng lặp cộng `List<Integer>` có thể đều là `O(n)`. Điều đó không bảo đảm thời gian, dung lượng hoặc lượng cấp phát giống nhau.

Ngược lại, thuật toán tìm kiếm tốt trên map wrapper có thể hiệu quả hơn thuật toán tuyến tính trên mảng primitive. Trước khi tối ưu boxing, phải chọn đúng cấu trúc và thuật toán cho yêu cầu.

## 10. Giảm chi phí mà vẫn giữ đúng mô hình dữ liệu

### 10.1. Giữ phép tính cục bộ ở primitive

Khi không cần biểu diễn `null`, biến đếm và cộng dồn thường nên là `int` hoặc `long` phù hợp miền giá trị.

Chỉ boxing khi phải đi qua API đối tượng. Cách đó làm ranh giới rõ hơn và tránh đặt biến trung gian trong một chu trình unbox–tính toán–box không cần thiết.

### 10.2. Chọn mảng primitive khi bài toán phù hợp

`int[]`, `long[]` hoặc `double[]` phù hợp khi:

- Dữ liệu chủ yếu phục vụ tính toán số.
- Có thể quản lý kích thước và cập nhật theo mô hình mảng.
- Không cần `null` cho từng phần tử.
- Không cần trực tiếp các ngữ nghĩa tập hợp hoặc ánh xạ của collection.

Không đổi mọi `List<Integer>` thành mảng chỉ vì nghe nói boxing tốn chi phí. Phải tính cả độ rõ ràng, tính linh hoạt và chi phí chuyển đổi ở ranh giới API.

### 10.3. Dùng primitive stream đúng chỗ

`IntStream`, `LongStream`, `DoubleStream` cung cấp luồng chuyên biệt cho số nguyên thủy.

Ví dụ:

```java
int sum = IntStream.of(1, 2, 3).sum();
```

Không cần biểu diễn từng phần tử trung gian bằng `Integer` trong một `Stream<Integer>` chỉ để cộng.

Nếu nguồn đã là danh sách wrapper:

```java
int sum = values.stream().mapToInt(Integer::intValue).sum();
```

vẫn cần unbox khi đi từ phần tử `Integer` sang `int`. Cách viết không tự xóa các wrapper đã nằm trong nguồn, và vẫn cần chính sách nếu có `null`.

Nếu tổng cần `long`, chọn dạng tính tổng tương ứng; `IntStream.sum()` trả `int` và không tự giải quyết mọi vấn đề tràn.

### 10.4. boxed đưa dữ liệu trở lại dạng đối tượng

Đoạn minh họa:

```java
List<Integer> result = IntStream.of(1, 2, 3).boxed().toList();
```

Phương thức `boxed()` chuyển luồng primitive sang luồng wrapper để tạo collection yêu cầu tham chiếu.

Không vừa chuyển sang primitive để tránh boxing, vừa gọi `boxed` ngay sau đó mà không có nhu cầu. Nhưng nếu API đầu ra cần `List<Integer>`, đây có thể là ranh giới hợp lý. Xem [IntStream Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html).

### 10.5. Dung lượng khởi tạo không loại boxing

`new ArrayList<Integer>(expectedSize)` có thể giảm số lần tăng sức chứa và sao chép vùng tham chiếu khi thêm nhiều phần tử.

Nó không biến vùng lưu trữ thành mảng `int`, không tự tạo trước các wrapper và không loại bỏ các chuyển đổi tại ranh giới phần tử.

Cần tách tối ưu sức chứa collection khỏi tối ưu kiểu biểu diễn phần tử.

### 10.6. Cấu trúc chuyên biệt primitive là một lựa chọn riêng

Khi dữ liệu số lớn và số liệu đo cho thấy wrapper là nút thắt, có thể đánh giá các cấu trúc chuyên biệt primitive. Đó có thể là mảng hoặc thư viện ngoài phù hợp.

Việc chọn thư viện cần xét API, ngữ nghĩa thiếu giá trị, khả năng tích hợp và chi phí chuyển đổi. Chuyên biệt primitive không tự bảo đảm phù hợp mọi yêu cầu nghiệp vụ.

## 11. Đo hiệu năng sao cho kết luận có giá trị

### 11.1. Đặt câu hỏi cụ thể

Không chỉ hỏi “boxing chậm bao nhiêu?”. Hãy chọn một công việc:

- Xây collection một lần rồi đọc nhiều lần.
- Thêm và xóa liên tục.
- Tính tổng trên dữ liệu đã có.
- Tra cứu khóa số.
- Cập nhật bộ đếm.
- Chuyển dữ liệu qua ranh giới API.

Mỗi công việc có thể có nguồn chi phí khác nhau.

### 11.2. Phân biệt dựng dữ liệu với xử lý dữ liệu

Nếu đang đo vòng lặp tính tổng, dựng `List<Integer>` bên ngoài hoặc bên trong phép đo là hai thí nghiệm khác nhau.

Nếu mục tiêu là toàn bộ đường xử lý của ứng dụng, chi phí dựng dữ liệu có thể phải được tính vào. Nếu mục tiêu là so sánh thao tác đọc, cần tách phần đó ra rõ ràng.

### 11.3. Dùng dữ liệu đại diện

Các yếu tố cần thay đổi có chủ đích:

- Kích thước dữ liệu.
- Giá trị nằm trong hoặc ngoài vùng cache thông dụng.
- Số lần lặp và mức tái sử dụng đối tượng.
- Có hoặc không có `null`.
- Tần suất đọc so với ghi.
- Kết quả có được giữ hoặc trả ra ngoài không.

Một thí nghiệm chỉ dùng các số nhỏ được lưu đệm dễ khiến kết luận về cấp phát không đại diện cho dữ liệu thật.

### 11.4. Tránh phép đo thủ công gây hiểu nhầm

Thời gian lần chạy đầu chịu ảnh hưởng nạp lớp, khởi tạo và biên dịch tối ưu. Mã không dùng kết quả có thể bị tối ưu theo cách làm thí nghiệm không còn đo công việc mong muốn.

Khi cần microbenchmark trên JVM, dùng công cụ chuyên dụng như [OpenJDK JMH](https://github.com/openjdk/jmh), với khởi động, các lượt chạy và cách tiêu thụ kết quả phù hợp. Theo dõi thêm lượng cấp phát hoặc GC nếu câu hỏi liên quan bộ nhớ.

Bài này không đưa ra con số chênh lệch thời gian hoặc dung lượng vì chúng cần môi trường, cấu hình JVM và khối lượng công việc cụ thể. Đo mới giúp quyết định thay đổi có đáng làm hay không.

## 12. Chương trình Java hoàn chỉnh

Chương trình sau quan sát boxing, unboxing, lựa chọn overload và các lỗi `null`. Nó không phải benchmark và không dùng thời gian chạy để suy ra chi phí.

Lưu vào tệp `BoxingInCollectionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.IntStream;

public class BoxingInCollectionsDemo {
    public static void main(String[] args) {
        List<Integer> scores = new ArrayList<>();
        scores.add(10);
        scores.add(20);

        int sum = 0;
        for (int score : scores) {
            sum += score;
        }
        System.out.println("scores: " + scores);
        System.out.println("primitive sum: " + sum);

        Integer smallA = 100;
        Integer smallB = 100;
        System.out.println("small cached identity: " + (smallA == smallB));

        Integer largeA = 1000;
        Integer largeB = 1000;
        System.out.println("large value equality: "
                + Objects.equals(largeA, largeB));

        Integer counter = 1000;
        Integer previous = counter;
        counter++;
        System.out.println("previous: " + previous + ", counter: " + counter);

        List<Integer> ids = new ArrayList<>(List.of(10, 20, 30));
        int removedByIndex = ids.remove(1);
        boolean removedByValue = ids.remove(Integer.valueOf(30));
        System.out.println("removed by index: " + removedByIndex);
        System.out.println("removed by value: " + removedByValue);
        System.out.println("remaining ids: " + ids);

        Map<String, Integer> counts = new HashMap<>();
        counts.put("known", 2);

        Integer missing = counts.get("missing");
        try {
            int count = missing;
            System.out.println("unexpected count: " + count);
        } catch (NullPointerException ex) {
            System.out.println("missing value unboxing: NullPointerException");
        }

        counts.put("unknown", null);
        try {
            int count = counts.getOrDefault("unknown", 0);
            System.out.println("unexpected default: " + count);
        } catch (NullPointerException ex) {
            System.out.println("mapped null with default: NullPointerException");
        }

        Integer optionalCount = counts.get("unknown");
        int safeCount = optionalCount == null ? 0 : optionalCount;
        System.out.println("explicit null policy: " + safeCount);

        Map<Integer, String> names = Map.of(1, "one");
        System.out.println("Integer key: " + names.get(1));
        System.out.println("Long key present: " + names.containsKey(1L));

        int streamSum = IntStream.of(1, 2, 3).sum();
        List<Integer> boxedValues = IntStream.of(1, 2, 3).boxed().toList();
        System.out.println("IntStream sum: " + streamSum);
        System.out.println("boxed stream values: " + boxedValues);

        List<Long> longValues = new ArrayList<>();
        longValues.add(1L);
        System.out.println("Long elements: " + longValues);

        Integer nullable = null;
        boolean useNullable = true;
        try {
            Integer chosen = useNullable ? nullable : 0;
            System.out.println("unexpected chosen: " + chosen);
        } catch (NullPointerException ex) {
            System.out.println("mixed conditional: NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 BoxingInCollectionsDemo.java
java BoxingInCollectionsDemo
```

Kết quả chuẩn:

```text
scores: [10, 20]
primitive sum: 30
small cached identity: true
large value equality: true
previous: 1000, counter: 1001
removed by index: 20
removed by value: true
remaining ids: [10]
missing value unboxing: NullPointerException
mapped null with default: NullPointerException
explicit null policy: 0
Integer key: one
Long key present: false
IntStream sum: 6
boxed stream values: [1, 2, 3]
Long elements: [1]
mixed conditional: NullPointerException
```

### 12.1. Ranh giới chuyển đổi

`scores.add(10)` và `scores.add(20)` cần boxing. Vòng lặp dùng biến `int score` cần unboxing phần tử đọc được.

Biến `sum` giữ giá trị nguyên thủy trong phép cộng, không cần giữ tổng bằng `Integer` ở mỗi lượt.

### 12.2. So sánh có chủ đích

Dòng `small cached identity` dùng hai hằng 100 nằm trong trường hợp được bảo đảm dùng chung tham chiếu.

Với 1000, chương trình chỉ in bình đẳng giá trị qua `Objects.equals`; nó không đóng đinh kết quả `==` vốn không nên được dùng làm quy tắc nghiệp vụ cho trường hợp này.

### 12.3. Lỗi null ở những vị trí khác nhau

Ba khối `try` tách riêng:

- Unbox kết quả thiếu từ map.
- Unbox giá trị `null` mà `getOrDefault` giữ lại vì khóa đã có.
- Unbox trong biểu thức điều kiện hỗn hợp wrapper–primitive.

Việc bắt ngoại lệ chỉ phục vụ thực nghiệm để chương trình tiếp tục in các trường hợp khác. Trong mã nghiệp vụ, nên quyết định chính sách dữ liệu trước và kiểm tra phù hợp, không dùng bắt `NullPointerException` làm cách xử lý thiếu giá trị thông thường.

### 12.4. API nhận Object không thống nhất các kiểu số

Map có khóa `Integer` tìm được `1`, nhưng không có khóa `Long` cho `1L`. Cả hai lời gọi đều biên dịch; kết quả khác nhau đến từ ngữ nghĩa kiểu và bình đẳng.

### 12.5. Primitive stream và ranh giới đầu ra

Tính tổng bằng `IntStream` làm việc trên luồng primitive. Khi gọi `boxed().toList()`, chương trình chủ động chuyển sang các phần tử wrapper cho kết quả dạng danh sách.

Không dùng output `[1, 2, 3]` để suy ra số đối tượng thực sự được cấp phát. Cần công cụ đo mới trả lời được câu hỏi đó trên JVM cụ thể.

## 13. Những lỗi cần nhận ra khi đọc mã collection số

### 13.1. Dùng wrapper chỉ vì collection dùng wrapper

Một danh sách cần `Integer` không có nghĩa mọi biến đếm, chỉ số hoặc kết quả tính toán trung gian cũng nên là `Integer`.

Giữ primitive ở nơi giá trị luôn tồn tại và chỉ boxing khi cần đi qua API tham chiếu.

### 13.2. Thay null bằng 0 mà không xét nghĩa

0 có thể là số lượng thật; `null` có thể là chưa biết, thiếu dữ liệu hoặc không áp dụng.

Nếu gộp các trạng thái này, chương trình có thể tránh ngoại lệ nhưng đưa ra kết quả nghiệp vụ sai. Chọn chính sách dữ liệu trước khi chọn biểu thức viết ngắn.

### 13.3. Dùng == vì một ví dụ số nhỏ chạy đúng

Cache khiến lỗi khó lộ trên dữ liệu nhỏ. Cần chọn phép so sánh theo mục đích: danh tính tham chiếu, giá trị cùng kiểu, hay so sánh số sau chuẩn hóa.

Không lấy kết quả của một giá trị làm quy tắc cho mọi wrapper.

### 13.4. Nghĩ ++ làm đối tượng Integer thay đổi tại chỗ

Wrapper là giá trị bất biến. Tăng biến wrapper có nghĩa cập nhật biến hoặc vị trí nhận kết quả, không sửa mọi tham chiếu đang cùng trỏ đối tượng cũ.

Trong một vòng `for-each` với biến `Integer value`, gọi `value++` không tự cập nhật phần tử trong list. Muốn thay nội dung collection phải dùng thao tác cập nhật phù hợp.

### 13.5. Tối ưu sai nguồn chi phí

Một chương trình chậm vì tìm tuyến tính lặp lại không nhất thiết được sửa bằng loại boxing. Một chương trình dùng quá nhiều bộ nhớ có thể còn do sức chứa lớn, các cấu trúc bao khác hoặc giữ dữ liệu không cần thiết.

Đo và phân tích toàn đường xử lý, đồng thời giữ nguyên kết quả nghiệp vụ khi thay biểu diễn.

## 14. Bài tập và tiêu chí tự kiểm tra

### Bài 1: Đánh dấu vị trí chuyển đổi

Với đoạn sau:

```java
List<Integer> values = new ArrayList<>();
values.add(5);
values.add(8);

long sum = 0;
for (int value : values) {
    sum += value;
}

Integer result = values.get(0) + values.get(1);
```

Hãy chỉ ra nơi boxing và unboxing.

Đáp án định hướng:

- Hai lần thêm literal cần boxing để phù hợp phần tử `Integer`.
- Biến vòng lặp `int` yêu cầu unboxing.
- Phép cộng cuối unbox hai giá trị, cộng theo kiểu số tương ứng rồi boxing kết quả cho biến `Integer`.
- Không suy ra số đối tượng cấp phát thực tế chỉ từ số chuyển đổi.

### Bài 2: Xây chính sách cho dữ liệu thiếu

Cho map có:

```text
"known"   -> 3
"unknown" -> null
"missing" -> không có ánh xạ
```

Thiết kế hai phiên bản:

1. Coi `unknown` và `missing` đều là 0.
2. Phân biệt thiếu khóa với có khóa nhưng chưa biết giá trị.

Cả hai phiên bản cần tránh unbox `null` ngoài ý muốn. Hãy giải thích vì sao một lời gọi `getOrDefault` chưa đủ để hiện thực cả hai chính sách.

### Bài 3: Xóa đúng số cần xóa

Từ danh sách `[1, 2, 3]`:

- Xóa phần tử ở chỉ số 1.
- Trên một bản danh sách mới, xóa giá trị 1.

Kết quả lần lượt phải là `[1, 3]` và `[2, 3]`. Ghi rõ kiểu của đối số cho từng overload.

### Bài 4: So sánh có xét null

Thiết kế kiểm tra hai `Integer` có cùng giá trị khi một hoặc cả hai có thể `null`.

Sau đó thử một `Integer` và một `Long` cùng giá trị số. Giải thích vì sao `Objects.equals` không tự biến chúng thành cùng kiểu.

### Bài 5: Phân tích thay vì đoán chi phí

Có một triệu giá trị số cần cộng nhiều lần. Hãy so sánh phương án:

- `int[]`.
- `List<Integer>`.
- Primitive stream trên mảng.
- Đọc danh sách bằng `mapToInt`.

Trước khi đo, ghi rõ có tính chi phí dựng dữ liệu không, kết quả dùng kiểu gì, có cần `null` không và dữ liệu nằm trong hay ngoài cache thông dụng.

Không viết kết luận nhanh hơn một tỉ lệ cố định nếu chưa có phép đo đại diện.

## 15. Câu hỏi cần tự trả lời được

1. Vì sao `List<Integer>` hợp lệ còn `List<int>` không hợp lệ trong Java 17?
2. Chỗ nào xảy ra chuyển đổi khi thêm `int` rồi đọc ra thành `int`?
3. Vì sao boxing không chắc luôn tạo đối tượng mới?
4. Vì sao unboxing `null` là lỗi thay vì nhận 0?
5. Tại sao `getOrDefault` vẫn có thể dẫn tới lỗi unboxing?
6. Vì sao hai wrapper so sánh bằng `==` khác wrapper so với primitive?
7. Cache có làm `==` trở thành phép so sánh giá trị đáng tin không?
8. `Integer` và `Long` cùng biểu diễn 1 có bằng nhau theo `equals` không?
9. Vì sao `remove(1)` trên `List<Integer>` xóa theo chỉ số?
10. Vì sao `List<Long>.add(1)` không được chuyển tự động theo chuỗi mở rộng rồi boxing?
11. Tại sao `Integer sum` trong vòng lặp có thêm ranh giới chuyển đổi so với `int sum`?
12. Những thành phần nào làm bộ nhớ của collection wrapper khác mảng primitive?
13. Khi nào `mapToInt` giúp giữ phần xử lý ở primitive, và khi nào `boxed` đưa dữ liệu trở lại dạng đối tượng?
14. Một microbenchmark cần kiểm soát điều gì để không đưa ra kết luận sai?

Điểm cần đạt là nhận ra ranh giới giữa giá trị nguyên thủy và tham chiếu đối tượng, xử lý `null` theo nghĩa dữ liệu, rồi đánh giá chi phí bằng toàn bộ cách tổ chức và xử lý dữ liệu. Autoboxing giúp viết gọn; nó không làm hai mô hình trở thành một.
