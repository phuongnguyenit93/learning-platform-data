# Selection collection: lọc phần tử theo điều kiện trên #this

## Mục tiêu

Collection selection trong Spring Expression Language (SpEL) cho phép lọc một tập hợp theo một điều kiện. Biểu thức selection được đánh giá lần lượt trên từng phần tử, và biến **#this** đại diện cho phần tử đang được xét. Kết quả chứa những phần tử thỏa điều kiện.

Selection hữu ích khi cần lấy các đơn hàng đang mở, thành viên thuộc một nhóm, sản phẩm vượt ngưỡng giá hoặc các entry trong Map đáp ứng một quy tắc. Nó giúp biểu diễn thao tác lọc gần với dữ liệu, nhưng vẫn cần hiểu rõ kiểu collection, thứ tự duyệt và cách xử lý null.

Sau bài này, bạn có thể:

- Dùng toán tử **.?[ ]** để lọc toàn bộ phần tử phù hợp.
- Hiểu vai trò của **#this** trong selection và phân biệt nó với **#root**.
- Dùng selection trên List, array, Iterable và Map.
- Chọn phần tử khớp đầu tiên hoặc cuối cùng bằng **.^[ ]** và **.$[ ]**.
- Kết hợp selection với property, biến và điều kiện logic.
- Phân biệt selection với projection và kiểm thử các trường hợp biên.

## 1. Cú pháp selection cơ bản

Cú pháp lọc toàn bộ phần tử:

~~~text
collection.?[selectionExpression]
~~~

Trong đó:

- **collection** là biểu thức trả về collection hoặc cấu trúc dữ liệu được SpEL hỗ trợ.
- **selectionExpression** là điều kiện được đánh giá cho từng phần tử.
- **#this** đại diện cho phần tử hiện tại trong lần đánh giá điều kiện đó.

Ví dụ:

~~~text
#root.orders.?[#this.total >= 100]
~~~

Biểu thức lấy danh sách orders từ root object, sau đó giữ lại các đơn hàng có total lớn hơn hoặc bằng 100.

Nếu một đơn hàng có total bằng 80, điều kiện trả về false và đơn hàng đó không xuất hiện trong kết quả. Nếu total bằng 120, điều kiện trả về true và đơn hàng được giữ lại.

Selection không sửa collection nguồn. Nó tạo kết quả lọc mới chứa những phần tử được chọn.

## 2. Hiểu đúng #this và #root

Trong SpEL, **#root** đại diện cho root object được truyền vào khi đánh giá biểu thức. **#this** đại diện cho object hiện tại trong ngữ cảnh đánh giá tại một thời điểm cụ thể.

Trong selection, SpEL lặp qua các phần tử và đánh giá điều kiện trên từng phần tử. Vì vậy, #this thay đổi theo phần tử đang được xét, còn #root vẫn trỏ tới root object ban đầu.

Giả sử root object là một cửa hàng có danh sách sản phẩm:

~~~java
public class Product {
    private String name;
    private BigDecimal price;
    private boolean available;

    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public boolean isAvailable() { return available; }
}

public class Store {
    private List<Product> products;

    public List<Product> getProducts() { return products; }
}
~~~

Có thể lọc sản phẩm còn hàng và có giá dưới 500:

~~~text
#root.products.?[#this.available and #this.price < 500]
~~~

Trong điều kiện:

- **#root.products** truy cập danh sách sản phẩm từ Store.
- **#this.available** đọc trạng thái của sản phẩm hiện tại.
- **#this.price** đọc giá của chính sản phẩm hiện tại.

Có thể viết ngắn hơn bằng cách dùng trực tiếp property của phần tử hiện tại:

~~~text
#root.products.?[available and price < 500]
~~~

Cả hai cách đều dùng phần tử hiện tại làm ngữ cảnh của điều kiện. Viết rõ #this hữu ích khi biểu thức có nhiều cấp lồng nhau hoặc khi muốn người đọc nhận ra ngay rằng điều kiện đang được áp dụng trên từng phần tử.

### Dùng root object trong điều kiện

Điều kiện selection có thể tham chiếu cả phần tử hiện tại lẫn dữ liệu ở root:

~~~text
#root.orders.?[#this.total >= #root.minimumTotal]
~~~

Ví dụ này giữ lại các đơn hàng có total đạt ngưỡng minimumTotal của root object. #this là Order hiện tại; #root vẫn là object chứa orders và minimumTotal.

Nếu ngưỡng được truyền qua biến trong EvaluationContext, có thể viết:

~~~text
#root.orders.?[#this.total >= #minimum]
~~~

Cách này tách dữ liệu cấu hình khỏi biểu thức và giúp bài kiểm thử thay đổi ngưỡng mà không phải tạo một chuỗi biểu thức khác.

## 3. Selection trên List và Iterable

Với List hoặc một Iterable được SpEL hỗ trợ, selection trả về một List mới gồm những phần tử thỏa điều kiện. Thứ tự phần tử được chọn theo thứ tự duyệt của collection nguồn.

Ví dụ:

~~~text
#root.members.?[#this.active]
~~~

Biểu thức trả về danh sách các thành viên có active là true.

Lọc theo một property String:

~~~text
#root.members.?[#this.department == 'Engineering']
~~~

Lọc theo nhiều điều kiện:

~~~text
#root.members.?[#this.active and #this.score >= 80]
~~~

Dùng ngoặc khi cần kết hợp AND và OR để thể hiện đúng nhóm điều kiện:

~~~text
#root.members.?[#this.active and (#this.role == 'ADMIN' or #this.role == 'REVIEWER')]
~~~

Điều kiện selection nên trả về Boolean. Nếu property có thể null, hãy xác định null có được xem như false, là dữ liệu không hợp lệ hay cần xử lý riêng. Đừng để một property null tạo ra hành vi ngoài dự kiến.

### Lọc một danh sách số

Nếu collection chứa các số, #this là giá trị số hiện tại:

~~~text
#root.values.?[#this > 10]
~~~

Biểu thức giữ lại các giá trị lớn hơn 10. Có thể kết hợp với điều kiện khác:

~~~text
#root.values.?[#this >= 10 and #this <= 100]
~~~

Kết quả là một List mới chứa các số trong khoảng từ 10 tới 100, bao gồm cả hai đầu mút.

## 4. Selection trên array

SpEL cũng hỗ trợ selection trên array. Kết quả là một List chứa các phần tử được chọn.

Ví dụ:

~~~text
#root.scores.?[#this >= 70]
~~~

Nếu scores là mảng số, biểu thức trả về danh sách các điểm từ 70 trở lên.

Không nhầm selection với truy cập index:

- **scores[0]** lấy một phần tử tại vị trí 0.
- **scores.?[#this >= 70]** lọc tất cả phần tử thỏa điều kiện.

Nếu array null, selection thông thường không thể duyệt phần tử. Từ Spring Framework 6.2, có thể dùng null-safe selection khi target có thể null; cú pháp được trình bày ở phần xử lý null.

## 5. Selection trên Map

Với Map, selection lọc các entry và trả về một Map mới chứa những entry được chọn. Mỗi entry có key và value. Trong điều kiện, **#this** đại diện cho entry đang được xét; có thể truy cập key và value của entry.

Ví dụ Map lưu giá sản phẩm theo mã:

~~~java
Map<String, BigDecimal> prices = new LinkedHashMap<>();
prices.put("PEN", new BigDecimal("5.00"));
prices.put("BOOK", new BigDecimal("120.00"));
prices.put("BAG", new BigDecimal("450.00"));
~~~

Lọc các entry có giá trên 100:

~~~text
#root.prices.?[#this.value > 100]
~~~

Kết quả giữ lại các cặp key/value tương ứng với BOOK và BAG.

Có thể lọc theo key:

~~~text
#root.prices.?[#this.key matches '[A-Z]{3}']
~~~

Hoặc kết hợp key và value:

~~~text
#root.prices.?[#this.key startsWith 'B' and #this.value >= 100]
~~~

Đối với Map, kết quả vẫn là Map để giữ liên hệ giữa key và value. Thứ tự duyệt phụ thuộc vào loại Map được sử dụng; nếu nghiệp vụ cần thứ tự ổn định, hãy chọn cấu trúc Map có quy định thứ tự như LinkedHashMap hoặc TreeMap.

## 6. Chọn phần tử đầu tiên hoặc cuối cùng

Ngoài việc lấy tất cả phần tử thỏa điều kiện, SpEL có hai toán tử selection chuyên biệt:

| Toán tử | Ý nghĩa |
|---|---|
| **.^[condition]** | Lấy phần tử khớp đầu tiên |
| **.$[condition]** | Lấy phần tử khớp cuối cùng |
| **.?[condition]** | Lấy tất cả phần tử khớp |

Ví dụ:

~~~text
#root.orders.^[#this.status == 'PAID']
~~~

Biểu thức lấy đơn hàng đầu tiên có trạng thái PAID theo thứ tự duyệt của collection.

Lấy đơn hàng PAID cuối cùng:

~~~text
#root.orders.$[#this.status == 'PAID']
~~~

Lấy tất cả đơn hàng PAID:

~~~text
#root.orders.?[#this.status == 'PAID']
~~~

Hai toán tử đầu phù hợp khi chỉ cần một kết quả. Nếu không có phần tử nào thỏa điều kiện, first/last selection trả về null. Vì thế, hãy xử lý trường hợp không tìm thấy trước khi tiếp tục truy cập property của kết quả.

Với List, thứ tự đầu/cuối là thứ tự phần tử trong List. Với Map, thứ tự phụ thuộc vào thứ tự duyệt entry của implementation Map. Không nên dùng first/last selection để biểu diễn ý nghĩa mới nhất/cũ nhất nếu collection không có thứ tự được bảo đảm.

## 7. Kết hợp selection với projection

Selection và projection đều thao tác trên collection nhưng có mục đích khác nhau:

- **Selection .?[ ]** lọc và giữ nguyên các phần tử được chọn.
- **Projection .![ ]** chuyển mỗi phần tử thành một giá trị khác.

Ví dụ lọc sản phẩm đang bán rồi lấy tên:

~~~text
#root.products.?[#this.available].![#this.name]
~~~

Các bước diễn ra theo thứ tự:

1. Selection giữ lại các sản phẩm có available là true.
2. Projection chạy trên danh sách kết quả.
3. Mỗi sản phẩm được chuyển thành giá trị name.
4. Kết quả cuối là danh sách tên sản phẩm.

Có thể viết selection và projection trên một dòng, nhưng khi biểu thức dài, hãy tách thành các biến hoặc biểu thức có tên trong ứng dụng để dễ đọc và kiểm thử.

Một ví dụ khác:

~~~text
#root.orders.?[#this.total >= #minimum].![#this.id]
~~~

Biểu thức lọc các đơn hàng đạt ngưỡng rồi trả về danh sách ID của chúng.

Không dùng projection nếu mục đích chỉ là lọc. Nếu viết **.?[#this.active]**, kết quả vẫn là các object ban đầu; nếu viết **.![#this.name]**, kết quả là các tên được chiếu từ object.

## 8. Xử lý null và collection rỗng

Selection cần một target có thể duyệt. Nếu target null, biểu thức selection thông thường có thể phát sinh lỗi đánh giá.

Từ Spring Framework 6.2, SpEL hỗ trợ null-safe selection:

~~~text
#root.orders?.?[#this.status == 'PAID']
~~~

Nếu orders null, biểu thức trả về null thay vì cố duyệt collection. Nếu orders tồn tại, SpEL thực hiện selection như bình thường.

Cú pháp null-safe cho first và last selection cũng có thể dùng:

~~~text
#root.orders?.^[#this.status == 'PAID']
#root.orders?.$[#this.status == 'PAID']
~~~

Hãy xác nhận phiên bản Spring Framework trước khi sử dụng các toán tử null-safe này. Chúng được bổ sung trong Spring Framework 6.2.

Collection rỗng khác collection null:

- Selection trên collection rỗng trả về collection kết quả rỗng.
- First/last selection trên collection rỗng không tìm được phần tử và trả về null.
- Selection trên target null cần null-safe selection nếu muốn nhận null thay vì lỗi.

Với điều kiện có property trung gian có thể null, xử lý riêng từng property:

~~~text
#root.orders.?[#this.customer?.active == true]
~~~

Ở đây, safe navigation bảo vệ customer null trên từng Order. Property active vẫn phải tồn tại và đọc được khi customer có giá trị.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy collection | Sai tên property hoặc root object không đúng | Kiểm tra root type và property path |
| Lỗi khi selection trên null | Collection target null | Xác thực dữ liệu hoặc dùng null-safe selection phù hợp phiên bản |
| Không có phần tử trong kết quả | Điều kiện không khớp dữ liệu nào | Kiểm tra predicate và dữ liệu đầu vào |
| Điều kiện lỗi khi đọc property | Phần tử hiện tại không có property hoặc property trung gian null | Kiểm tra kiểu phần tử và dùng safe navigation khi phù hợp |
| Dùng nhầm #root và #this | Điều kiện đọc sai object | Xác định root object và phần tử hiện tại |
| Map selection trả kết quả không như mong đợi | Đang lọc nhầm key/value hoặc kỳ vọng List thay vì Map | Kiểm tra Map.Entry và kiểu kết quả |
| First/last trả null | Không có phần tử phù hợp | Xử lý trường hợp không tìm thấy trước khi truy cập tiếp |
| Kết quả thay đổi theo môi trường | Collection hoặc thứ tự duyệt khác nhau | Xác định cấu trúc nguồn và quy tắc ordering |

Khi predicate phức tạp, hãy kiểm tra nó trên một phần tử đơn lẻ trước. Sau đó mới đặt điều kiện vào selection để xác định lỗi đến từ property, phép so sánh hay collection traversal.

## 10. Kiểm thử selection

Một bài kiểm thử nên xác minh số lượng phần tử được chọn, nội dung và thứ tự kết quả.

Ví dụ:

~~~java
@Test
void selectsActiveMembers() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
        parser.parseExpression("#root.members.?[#this.active]");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    Team team = new Team(List.of(
        new Member("Lan", true),
        new Member("Minh", false),
        new Member("An", true)
    ));

    List<?> selected = expression.getValue(context, team, List.class);

    assertEquals(2, selected.size());
}
~~~

Với từng loại nguồn, hãy chuẩn bị các trường hợp:

| Trường hợp | Điều cần xác minh |
|---|---|
| Mọi phần tử đều khớp | Kết quả giữ tất cả phần tử |
| Không phần tử nào khớp | Kết quả rỗng |
| Chỉ phần tử đầu khớp | Kết quả đúng thứ tự |
| Chỉ phần tử cuối khớp | Kết quả đúng thứ tự |
| Nhiều phần tử khớp | Không mất hoặc lặp phần tử |
| Predicate có biến ngoài | Biến được cung cấp đúng trong context |
| Property phần tử null | Điều kiện xử lý null theo hợp đồng |
| Collection null | Lỗi hoặc null-safe behavior được xác định |
| Collection rỗng | Selection trả kết quả rỗng |
| Map | Giữ đúng key/value của entry được chọn |
| First/last không tìm thấy | Kết quả null được xử lý |

Đối với Map, kiểm tra cả key lẫn value và xác nhận kiểu kết quả là Map. Đối với List, xác nhận thứ tự phần tử được chọn theo thứ tự nguồn.

## 11. Thực hành tốt

- Dùng selection khi mục đích là lọc phần tử, dùng projection khi mục đích là chuyển đổi phần tử.
- Viết điều kiện rõ ràng và ưu tiên một vài điều kiện nghiệp vụ dễ đọc.
- Dùng #this để chỉ rõ phần tử đang được xét trong predicate.
- Dùng #root khi cần dữ liệu từ root object.
- Kiểm tra kiểu phần tử và property mà predicate truy cập.
- Xử lý null riêng biệt; không giả định safe navigation sửa được mọi lỗi trong predicate.
- Dùng ^ và $ khi chỉ cần phần tử đầu hoặc cuối, đồng thời quy định thứ tự collection.
- Với Map, hiểu kết quả selection giữ lại entry thay vì chỉ trả danh sách value.
- Tránh gọi method có tác dụng phụ trong predicate vì selection có thể gọi điều kiện nhiều lần.
- Kiểm thử collection rỗng, không có kết quả, nhiều kết quả và dữ liệu null.
- Nếu predicate được cấu hình ngoài mã nguồn, parse và đánh giá nó với dữ liệu mẫu trước khi kích hoạt.

## 12. Checklist review

Trước khi chấp nhận biểu thức selection, hãy kiểm tra:

- [ ] Target là collection/array/Map được SpEL hỗ trợ.
- [ ] Predicate trả về Boolean theo ý nghĩa nghiệp vụ.
- [ ] #this đại diện đúng phần tử hiện tại.
- [ ] #root được dùng khi cần dữ liệu từ root object.
- [ ] Property và kiểu dữ liệu của phần tử đã được xác định.
- [ ] Map selection kiểm tra đúng key hoặc value.
- [ ] Kết quả mong đợi là List hay Map đã được xác định.
- [ ] Thứ tự nguồn đủ ổn định nếu dùng first/last selection.
- [ ] Collection null và collection rỗng được xử lý riêng.
- [ ] Safe navigation được hỗ trợ bởi phiên bản Spring đang chạy.
- [ ] Selection được phân biệt rõ với projection.
- [ ] Có kiểm thử cho kết quả rỗng, nhiều phần tử, null và Map.

## Kết luận

Collection selection trong SpEL dùng **.?[condition]** để lọc phần tử, trong đó **#this** là phần tử hiện tại và **#root** vẫn là object gốc. Selection trên List, array và Iterable tạo danh sách phần tử được chọn; selection trên Map giữ lại các entry phù hợp. Dùng **.^[ ]** hoặc **.$[ ]** khi chỉ cần phần tử đầu/cuối theo thứ tự duyệt. Khi kết hợp với projection, null-safe selection và biến bên ngoài, hãy xác định rõ kiểu nguồn, hành vi null, thứ tự và kiểu kết quả để biểu thức dễ hiểu và có thể kiểm thử.
