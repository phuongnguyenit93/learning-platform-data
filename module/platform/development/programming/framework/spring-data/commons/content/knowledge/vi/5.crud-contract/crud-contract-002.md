# saveAll, collection đầu vào và đối tượng được trả về

## 1. Một lời gọi lưu nhiều đối tượng có những hợp đồng nào?

Trong một màn hình nhập sản phẩm, ứng dụng có thể tạo nhiều đối tượng rồi gọi:

```java
Iterable<Product> saved = products.saveAll(input);
```

Câu lệnh ngắn này thường dẫn đến những giả định chưa được kiểm chứng:

- Kết quả chắc chắn là chính collection đầu vào.
- Đối tượng trả về luôn là cùng instance đã truyền vào.
- Kết quả chắc chắn giữ thứ tự để ghép theo chỉ số.
- Có bao nhiêu phần tử thì cơ sở dữ liệu chèn bấy nhiêu dòng mới.
- Lưu nhiều đối tượng đồng nghĩa một lệnh bulk duy nhất.
- Khi phương thức trả về thì mọi thay đổi đã commit.

Hợp đồng Commons không đưa ra tất cả những bảo đảm đó.

Trong module **SPRING_DATA_COMMONS**, cần hiểu rõ phần giao diện chung của CRUD, rồi đối chiếu cách thực hiện với store module, mapping và transaction cụ thể. Bài này tập trung vào đầu vào của `saveAll`, đối tượng được trả về và cách sử dụng kết quả mà không phụ thuộc những giả định ngoài hợp đồng.

## 2. Chữ ký chuẩn và ý nghĩa generic

### 2.1. CrudRepository

Hợp đồng của `CrudRepository<T, ID>` có phương thức:

```java
<S extends T> Iterable<S> saveAll(Iterable<S> entities);
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `T` | Kiểu domain mà repository quản lý |
| `S extends T` | Kiểu đối tượng cụ thể được truyền trong lời gọi |
| `Iterable<S> entities` | Nguồn phần tử cần lưu |
| `Iterable<S>` trả về | Các đối tượng sau khi được lưu theo cơ chế của store |

`saveAll` thuộc nhóm thao tác ghi. Nó không phải derived query được phân tích từ tên phương thức như `findBySku`.

Generic `S` giữ quan hệ kiểu giữa đầu vào và kết quả ở cấp Java. Nó không làm mọi kiểu con của domain tự trở thành kiểu được store mapping hỗ trợ. Nếu sử dụng kế thừa domain, cần có mapping phù hợp.

### 2.2. ListCrudRepository

Trong những phiên bản có `ListCrudRepository<T, ID>`, biến thể của hợp đồng trả về danh sách là:

```java
<S extends T> java.util.List<S> saveAll(
        Iterable<S> entities
);
```

Đầu vào vẫn là `Iterable`. Sự khác biệt nằm ở kiểu collection trả về.

Một repository cụ thể của store cũng có thể công khai kiểu trả về danh sách qua hệ thống kế thừa của nó. Khi viết code, hãy xem đúng interface và phiên bản đang dùng thay vì suy từ tên method.

Ngay cả khi kết quả có kiểu `List`, không tự suy ra hợp đồng ghép từng vị trí với đầu vào. Danh sách có vị trí để truy cập không đồng nghĩa vị trí đó được Commons cam kết tương ứng với một vị trí của collection nguồn.

## 3. Những bảo đảm cần nắm trước

Ở cấp hợp đồng CRUD chung:

| Nội dung | Cách hiểu |
| --- | --- |
| Đối số `entities` | Không được null |
| Phần tử trong đối số | Không được chứa phần tử null |
| Kết quả thành công | Có kết quả trả về, không dùng null để biểu đạt “không lưu được gì” |
| Số phần tử kết quả | Bằng số phần tử đầu vào theo hợp đồng |
| Collection kết quả | Không được giả định là chính collection đầu vào |
| Instance phần tử | Không được giả định luôn là chính instance đầu vào |
| Thứ tự tương ứng | Không dựa vào một bảo đảm chung về thứ tự mà hợp đồng không nêu |
| Số câu lệnh hoặc transaction | Cần xem implementation, cấu hình và store |

Điều kiện “kết quả thành công” rất quan trọng. Nếu thao tác ném exception, bạn không nhận được một collection kết quả bình thường để suy ra phần nào đã thành công.

Số phần tử bằng nhau cũng không phải số bản ghi được insert. Đầu vào có thể chứa đối tượng mới, đối tượng cần cập nhật hoặc nhiều biểu diễn liên quan đến cùng một định danh.

## 4. Iterable không đồng nghĩa List

### 4.1. Những đầu vào thường gặp

```java
List<Product> productsToSave = ...;
Set<Product> distinctProducts = ...;
Iterable<Product> source = ...;
```

Cả List và Set đều là Iterable. Một nguồn tùy chỉnh cũng có thể thực hiện Iterable mà không phải Collection.

| Đầu vào | Điều cần chú ý |
| --- | --- |
| ArrayList | Có thứ tự duyệt của danh sách; vẫn không tự bảo đảm thứ tự tương ứng ở đầu ra |
| List không sửa được cấu trúc | Không cần thêm hoặc xóa phần tử để chỉ duyệt và lưu |
| HashSet | Không có thứ tự duyệt được bảo đảm; có thể đã loại phần tử theo equals/hashCode |
| LinkedHashSet | Có thứ tự duyệt riêng, nhưng không tạo thêm cam kết từ saveAll |
| Iterable tùy chỉnh | Cần hiểu số lần có thể duyệt, chi phí và vòng đời nguồn |
| Nguồn rất lớn | Cần đánh giá bộ nhớ, kích thước lô và transaction |

Không thể gọi `size()` lên một biến có kiểu Iterable chỉ vì dữ liệu bên dưới thường là List. Giao diện Iterable không có phương thức đó.

### 4.2. List không sửa được cấu trúc vẫn chứa đối tượng có thể thay đổi

Ví dụ:

```java
List<Product> input = List.of(firstProduct, secondProduct);
Iterable<Product> saved = products.saveAll(input);
```

Ví dụ `List.of` yêu cầu Java có API này. Collection không cho thêm, xóa hoặc thay phần tử qua các thao tác cấu trúc của nó.

Điều đó không làm `firstProduct` và `secondProduct` bất biến. Một implementation có thể gán ID, version hoặc các giá trị khác lên đối tượng theo cơ chế của store.

Cần phân biệt:

```text
Tính thay đổi được của collection
        khác với
Tính thay đổi được của đối tượng trong collection
```

Không cần đổi mọi đầu vào thành ArrayList chỉ vì nghĩ saveAll phải gọi add hoặc remove trên collection nguồn. Tuy nhiên, một bản sao có thể hữu ích nếu mục tiêu là chốt một ảnh chụp của danh sách trước khi xử lý.

### 4.3. Sao chép danh sách không phải sao chép đối tượng

```java
List<Product> snapshot = new ArrayList<>(incoming);
```

Nếu `incoming` là Collection, đoạn code tạo một container mới nhưng vẫn chứa các tham chiếu tới cùng các Product.

Việc thay đổi cấu trúc `incoming` sau đó không làm cấu trúc snapshot đổi theo. Nhưng việc sửa Product qua một tham chiếu vẫn có thể được nhìn thấy qua tham chiếu trong snapshot.

Khi cần đóng băng dữ liệu một yêu cầu nhập, hãy thiết kế command hoặc bản sao dữ liệu phù hợp. Không coi sao chép collection là một deep copy.

## 5. Null, đầu vào rỗng và nguồn chỉ dùng một lần

### 5.1. Null không phải danh sách rỗng

```java
products.saveAll(null);
```

Đây là vi phạm điều kiện đầu vào. Hợp đồng yêu cầu đối số và từng phần tử đều khác null; lỗi đối số không hợp lệ có thể được báo bằng `IllegalArgumentException`.

Tương tự:

```java
List<Product> invalid = new ArrayList<>();
invalid.add(firstProduct);
invalid.add(null);

products.saveAll(invalid);
```

Không dùng null như một cách yêu cầu “bỏ qua dòng nhập này”. Hãy lọc hoặc từ chối dòng không hợp lệ trước khi lưu theo quy tắc của ứng dụng.

Nếu dùng `List.of(firstProduct, null)`, lỗi có thể xuất hiện ngay tại bước tạo List vì List.of không chấp nhận null. Khi đó chưa có lời gọi repository nào được thực hiện.

### 5.2. Đầu vào rỗng là một trường hợp hợp lệ

```java
Iterable<Product> saved =
        products.saveAll(java.util.Collections.emptyList());
```

Khi đầu vào không có phần tử, kết quả thành công cũng không có phần tử theo hợp đồng về số lượng.

Không suy từ đó rằng mọi implementation chắc chắn tạo cùng số thao tác hạ tầng hoặc cùng số dòng log. Điều cần dựa vào ở cấp ứng dụng là không có đối tượng kết quả cần xử lý.

### 5.3. Không mặc định Iterable chỉ bị duyệt đúng một lần

Một implementation có thể cần khảo sát phần tử để chọn chiến lược lưu rồi tiếp tục xử lý nguồn. Hợp đồng chung không hứa chỉ gọi iterator đúng một lần.

Một wrapper tạo từ Stream có thể gặp vấn đề:

```java
Iterable<Product> oneShot = stream::iterator;
```

Stream là nguồn chỉ được sử dụng một lần. Việc bọc nó thành Iterable không biến nó thành một nguồn có thể lặp lại tùy ý.

Nếu muốn truyền dữ liệu từ một Stream hữu hạn, cân nhắc thu thập thành một collection ổn định trước, đồng thời quản lý tài nguyên và kích thước dữ liệu phù hợp.

Không truyền một nguồn vô hạn cho thao tác lưu nhiều đối tượng với kỳ vọng phương thức tự tìm điểm dừng.

### 5.4. Vật hóa một nguồn hữu hạn và kiểm tra null trước

Một helper của ứng dụng có thể chốt dữ liệu đầu vào:

```java
static <T> List<T> materialize(
        Iterable<? extends T> source
) {
    if (source == null) {
        throw new IllegalArgumentException(
                "Nguồn dữ liệu không được null"
        );
    }

    List<T> result = new ArrayList<>();

    for (T item : source) {
        if (item == null) {
            throw new IllegalArgumentException(
                    "Phần tử không được null"
            );
        }
        result.add(item);
    }

    return result;
}
```

Helper đọc nguồn một lần rồi tạo List có thể duyệt lại. Đổi lại, nó cần bộ nhớ tương ứng với toàn bộ dữ liệu.

Kiểm tra null sớm giúp tránh bắt đầu ghi rồi mới gặp một phần tử null ở cuối nguồn. Nó không bảo đảm mọi điều kiện dữ liệu, ràng buộc cơ sở dữ liệu hoặc xung đột đồng thời đều đã được xử lý.

## 6. Dùng các đối tượng được trả về sau khi lưu

### 6.1. Cách dùng cơ bản

Giả sử Product có constructor nhận SKU, tên, giá và có các getter tương ứng. Mapping, định danh và repository của store đã được cấu hình.

```java
List<Product> input = List.of(
        new Product(
                "KEY-001",
                "Bàn phím cơ",
                new BigDecimal("1200000")
        ),
        new Product(
                "MOU-001",
                "Chuột không dây",
                new BigDecimal("450000")
        )
);

Iterable<Product> saved = products.saveAll(input);

for (Product product : saved) {
    // Dùng đối tượng sau lưu để tạo kết quả hoặc xử lý tiếp.
    handleSavedProduct(product);
}
```

`handleSavedProduct` ở đây đại diện cho bước xử lý kết quả của ứng dụng, không phải phương thức Spring Data.

Điểm chính là vòng lặp xử lý `saved`, không tiếp tục coi `input` là nguồn duy nhất của trạng thái sau lưu.

### 6.2. Vì sao instance có thể khác?

Một store có thể:

- Bổ sung ID hoặc version.
- Trả về một biểu diễn khác sau chuyển đổi.
- Trả về một đối tượng đang được quản lý thay cho đối tượng đầu vào.
- Áp dụng callback hoặc auditing trong đường lưu được cấu hình.

Không có quy tắc Commons rằng mọi trường hợp đều sửa trực tiếp đối tượng đầu vào và trả lại chính nó.

Trong JPA, sự khác biệt có thể thấy khi implementation dùng `merge`: đối tượng được trả về là instance được quản lý, còn đối tượng truyền vào không tự trở thành instance được quản lý chỉ vì đã được merge.

Với đường `persist` cho entity mới, bạn có thể thường quan sát chính instance đầu vào được quản lý và nhận ID theo chiến lược định danh. Đó là hành vi theo đường thực thi JPA, không phải cam kết chung cho mọi store.

### 6.3. Một lỗi dễ mắc

```java
products.saveAll(input);

// Tiếp tục đọc input và giả định toàn bộ trạng thái sau lưu
// đều đã được cập nhật trực tiếp lên từng instance ban đầu.
```

Code có thể trông đúng trong một tình huống tạo mới, rồi sai khi chuyển sang đối tượng detached, cách mapping khác hoặc một store khác.

Cách chắc chắn hơn về mặt hợp đồng là giữ kết quả và dùng các phần tử từ kết quả đó:

```java
Iterable<Product> saved = products.saveAll(input);
```

Nếu tầng tiếp theo cần List, thu thập tường minh:

```java
List<Product> savedList = new ArrayList<>();
saved.forEach(savedList::add);
```

Không ép `Iterable<Product>` thành `List<Product>` nếu interface repository không bảo đảm điều đó.

### 6.4. Đối tượng trả về không tự là bản chụp bất biến

Một List kết quả có thể chứa các entity có thể thay đổi. Thu thập lại thành List mới chỉ thay container, không đóng băng trạng thái từng entity.

Nếu cần trả dữ liệu ổn định cho API hoặc một bước xử lý tách biệt, hãy tạo DTO từ trạng thái cần thiết của các đối tượng trả về, theo ranh giới transaction và quy tắc tải dữ liệu của store.

Đừng mặc định có thể sửa cấu trúc collection kết quả bằng add hoặc remove. Kiểu List nói về hợp đồng danh sách, không tự bảo đảm implementation luôn hỗ trợ mọi thao tác thay đổi.

## 7. Ba loại “giống nhau” phải được tách biệt

| Câu hỏi | Ý nghĩa |
| --- | --- |
| Hai collection có cùng số phần tử không? | Cardinality của đầu vào và kết quả |
| Hai phần tử có cùng định danh nghiệp vụ hoặc persistence ID không? | Cùng đối tượng dữ liệu theo tiêu chí đã chọn |
| Hai tham chiếu có trỏ đúng cùng instance Java không? | Identity của đối tượng trong bộ nhớ |

Một kết quả có thể có cùng số phần tử nhưng chứa các instance khác. Hai instance khác nhau có thể biểu diễn cùng một định danh. Hai vị trí trong một collection cũng có thể cùng trỏ tới một instance.

`saveAll` không yêu cầu ứng dụng đồng nhất ba khái niệm này.

Đừng dùng toán tử `==` để kết luận hai đối tượng không đại diện cho cùng bản ghi chỉ vì store trả về một instance khác.

Ngược lại, phương thức `equals` của domain phải được thiết kế theo nhu cầu của domain và mapping; repository không tự sửa một triển khai equals/hashCode không phù hợp.

## 8. Không ghép đầu vào và kết quả theo chỉ số nếu thiếu bảo đảm

### 8.1. Một cách ghép mong manh

```text
input[0] tương ứng saved[0]
input[1] tương ứng saved[1]
...
```

Một implementation cụ thể có thể hiện thực bằng cách duyệt đầu vào rồi thêm kết quả lần lượt vào List. Điều quan sát được đó không tự biến thành bảo đảm về thứ tự của hợp đồng Commons.

Ngay cả đầu vào là ArrayList cũng chỉ xác định thứ tự duyệt của đầu vào. Nó không thêm một cam kết vào API của repository.

Nếu một API của store hoặc một phương thức cụ thể thực sự cam kết thứ tự, có thể sử dụng trong đúng phạm vi đó và ghi rõ sự phụ thuộc. Không suy ra chỉ từ kiểu List của kết quả.

### 8.2. Ghép bằng một khóa ổn định

Giả sử quy trình nhập sản phẩm có quy tắc:

- Mỗi SKU xuất hiện tối đa một lần trong lô.
- SKU đã được chuẩn hóa trước khi lưu.
- SKU không bị thay đổi bởi callback hoặc converter khi lưu.
- Dữ liệu lưu có ràng buộc duy nhất phù hợp cho SKU.

Khi đó có thể ghép bằng SKU thay vì chỉ số:

```java
List<Product> input = materialize(source);
ensureUniqueSku(input);

Iterable<Product> saved = products.saveAll(input);

Map<String, Product> savedBySku = new HashMap<>();

for (Product product : saved) {
    savedBySku.put(product.getSku(), product);
}

Product savedKeyboard = savedBySku.get("KEY-001");
```

`source` là nguồn hữu hạn đầu vào, `materialize` là helper ở phần trước, còn helper kiểm tra SKU có thể là:

```java
static void ensureUniqueSku(List<Product> input) {
    Set<String> seen = new HashSet<>();

    for (Product product : input) {
        String sku = product.getSku();

        if (sku == null || sku.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "SKU không được rỗng"
            );
        }

        if (!seen.add(sku)) {
            throw new IllegalArgumentException(
                    "SKU xuất hiện nhiều lần trong lô"
            );
        }
    }
}
```

Ví dụ giả định SKU đã chuẩn hóa nên việc so sánh String ở helper khớp quy tắc nghiệp vụ. Nếu cơ sở dữ liệu đối chiếu SKU khác chữ hoa/chữ thường so với ứng dụng, cần thống nhất quy tắc đó.

Kiểm tra trùng trong lô không thay thế ràng buộc duy nhất tại kho dữ liệu. Một yêu cầu khác có thể ghi cùng SKU đồng thời.

### 8.3. Khi chưa có khóa để ghép

Với đối tượng mới, mọi ID đầu vào có thể đang null. Bạn không thể tạo một map theo các ID null để ghép từng đối tượng một cách duy nhất.

Cần thiết kế trước một trong các cơ chế phù hợp:

- Khóa nghiệp vụ ổn định như SKU.
- Định danh được cấp trước theo chiến lược store hỗ trợ.
- Một mã tương quan được đưa qua đường lưu và có thể lấy lại theo thiết kế.

Một mã chỉ có trong request nhưng không đi qua bất kỳ cơ chế lưu hoặc chuyển đổi nào sẽ không tự xuất hiện trong kết quả.

Nếu nghiệp vụ cần trả kết quả theo thứ tự request, có thể giữ danh sách khóa của request rồi dựng DTO kết quả theo danh sách khóa đó. Đây là thứ tự do ứng dụng chủ động tạo, không phải thứ tự được mặc định cho saveAll.

## 9. Phần tử trùng và nhiều đối tượng cùng ID

### 9.1. List có thể chứa cùng một tham chiếu nhiều lần

```java
List<Product> input = List.of(product, product);
```

Đầu vào có hai phần tử theo nghĩa hai vị trí. Chúng lại là cùng một instance Java.

Không thể suy ra có hai sản phẩm riêng biệt cần được tạo. Store có thể xử lý cùng đối tượng theo trạng thái của nó, và kết quả có thể chứa các tham chiếu trùng nhau.

Cardinality của kết quả không phải số entity duy nhất và không phải số bản ghi mới.

### 9.2. Hai instance có thể cùng một persistence ID

Nếu hai đối tượng đầu vào cùng biểu diễn một định danh, kết quả có thể phụ thuộc:

- Cách store xử lý trạng thái đối tượng.
- Version dùng cho optimistic locking, nếu có.
- Quy tắc xung đột trong persistence context hoặc cơ chế tương ứng.
- Thứ tự và cách implementation thực hiện thao tác ghi.

Không dùng saveAll để ngầm chọn “đối tượng cuối cùng sẽ thắng”. Nếu một lô chỉ được phép có một thay đổi cho mỗi ID, hãy kiểm tra điều đó trước khi gọi repository.

### 9.3. Set không phải công cụ tự động làm dữ liệu hợp lệ

HashSet loại phần tử theo equals/hashCode của Java. Điều đó không nhất thiết trùng với quy tắc SKU duy nhất hoặc ID duy nhất của nghiệp vụ.

Ví dụ, nếu equals coi hai đối tượng mới có ID null là bằng nhau, Set có thể làm mất một dòng nhập trước cả khi saveAll được gọi.

Nếu hashCode phụ thuộc vào ID hoặc version bị thay đổi khi lưu, đối tượng đã nằm trong HashSet có thể không còn được tra cứu đúng theo cấu trúc băm sau khi thuộc tính thay đổi.

Dùng cấu trúc đầu vào phản ánh đúng ý định, rồi kiểm tra khóa nghiệp vụ tường minh. Đừng đổi List thành Set chỉ để che một lỗi trùng chưa được giải thích.

## 10. saveAll không tự đồng nghĩa bulk hoặc batch

### 10.1. Ba khái niệm khác nhau

| Khái niệm | Ý nghĩa |
| --- | --- |
| `saveAll` | API yêu cầu lưu nhiều đối tượng |
| Batching của provider/driver | Gom việc truyền hoặc thực hiện nhiều thao tác theo cơ chế cụ thể |
| Bulk operation của store | Một API hoặc lệnh xử lý nhiều dữ liệu theo mô hình riêng của store |

Một implementation saveAll có thể duyệt các đối tượng rồi dùng cơ chế lưu từng đối tượng. Provider hoặc driver phía dưới có thể gom một số thao tác, nhưng điều đó còn phụ thuộc cấu hình và mapping.

Một implementation khác có thể chọn đường ghi nhiều đối tượng khi thấy các điều kiện thích hợp.

Không có công thức chung:

```text
1 lần gọi saveAll = 1 câu SQL = 1 lượt mạng
```

Cũng không có công thức:

```text
N phần tử = N insert
```

Đầu vào có thể gồm cả tạo mới và cập nhật. Cơ chế xác định đối tượng mới, optimistic locking, callback, auditing hoặc mapping có thể làm phát sinh thao tác bổ sung.

### 10.2. Ví dụ với JPA

Trong đường JPA thông thường, implementation cơ sở có thể xử lý từng entity qua cơ chế lưu phù hợp. Provider như Hibernate quyết định việc tạo SQL và batching theo cấu hình cùng chiến lược định danh.

Nếu muốn biết saveAll đã giảm số lượt truy cập hay chưa, cần quan sát ở mức provider/driver phù hợp. Số phần tử của List kết quả không cho biết số SQL hoặc số lượt mạng.

Log SQL đơn thuần cũng chưa luôn phản ánh đầy đủ cách driver gom batch. Cần chọn bằng chứng phù hợp với câu hỏi hiệu năng đang đo.

### 10.3. Chia lô là quyết định của ứng dụng

Khi dữ liệu lớn, có thể chia nguồn hữu hạn thành các lô có kích thước kiểm soát được.

Nhưng chia List thành nhiều phần không tự:

- Tạo một transaction riêng cho từng lô.
- Giải phóng persistence context.
- Bảo đảm mỗi lô chỉ có một thao tác ghi vật lý.
- Giữ nguyên tính nguyên tử trên toàn bộ lần nhập.

Nếu dùng JPA và cần flush/clear giữa các lô, phải xử lý trạng thái entity và kết quả trả về theo đúng vòng đời. Đó là thiết kế theo store, không nên giấu trong một helper generic rồi áp dụng cho mọi kho dữ liệu.

## 11. Kết quả trả về, flush và commit là ba thời điểm khác nhau

### 11.1. Có kết quả chưa chắc đã commit

Một lời gọi saveAll có thể diễn ra bên trong transaction đang mở. Sau khi có kết quả, transaction vẫn còn công việc khác và có thể thất bại trước khi commit.

Vì vậy:

- Nhận được một ID không tự chứng minh bản ghi đã commit.
- Có instance sau lưu không đồng nghĩa mọi thay đổi đã bền vững.
- Exception liên quan ràng buộc hoặc đồng bộ dữ liệu có thể xuất hiện muộn hơn, tùy store và thời điểm thực thi.

Một ID đã được cấp cũng có thể còn nằm trên đối tượng Java sau khi transaction rollback. Không dùng riêng việc ID khác null để kết luận lần nhập trước đã thành công.

### 11.2. saveAllAndFlush thuộc nhánh JPA

Một số repository JPA công khai `saveAllAndFlush`. Nó kết hợp lưu và yêu cầu flush trong đường thực thi JPA tương ứng.

Flush đồng bộ thay đổi xuống cơ sở dữ liệu trong transaction; nó không tự đồng nghĩa commit.

Việc flush một persistence context còn có thể đồng bộ các thay đổi đang chờ khác trong context, không chỉ những entity vừa có mặt trong tham số của saveAll.

Không thêm phương thức này vào hợp đồng Commons chung rồi mặc định mọi store đều có cùng ngữ nghĩa.

### 11.3. Đối tượng trả về không tự chứa mọi giá trị do database sinh

ID, version và auditing có thể được bổ sung theo mapping và đường lưu. Nhưng một giá trị do default hoặc trigger của cơ sở dữ liệu tạo ra không chắc đã tự được nạp lại đầy đủ lên đối tượng trả về.

Nếu bước tiếp theo cần một trường như vậy, cần xem khả năng trả giá trị sinh, refresh hoặc đọc lại mà store hỗ trợ.

Không dùng việc thu thập Iterable thành List như một cơ chế refresh. Đoạn thu thập chỉ làm việc với các phần tử của kết quả, không thay thế một thao tác đọc lại được thiết kế rõ ràng.

## 12. Khi một phần tử gây lỗi

### 12.1. Không có bảo đảm nguyên tử chỉ từ chữ ký

Một phần tử có thể làm thao tác thất bại vì:

- Ràng buộc dữ liệu bị vi phạm.
- Optimistic locking phát hiện xung đột ở store có hỗ trợ.
- Mapping hoặc chuyển đổi dữ liệu không hợp lệ.
- Kho dữ liệu hoặc kết nối gặp lỗi.

Chữ ký saveAll không đủ để kết luận mọi phần tử trước đó đã commit hay tất cả đã rollback.

Cần xem transaction boundary, khả năng của store và cách implementation thực hiện thao tác.

Trong cấu hình JPA thông thường, phương thức cơ sở được tích hợp transaction. Nếu tham gia một transaction ngoài, thời điểm commit hoặc rollback cuối cùng thuộc ranh giới transaction đó.

Với store hoặc cấu hình khác, không được mang nguyên kết luận từ JPA sang áp dụng.

### 12.2. Validation sớm không thay thế transaction

Helper materialize có thể phát hiện null trước khi ghi. Helper ensureUniqueSku có thể phát hiện trùng SKU trong cùng lô trước khi ghi.

Chúng không phát hiện chắc chắn mọi ràng buộc hoặc cập nhật đồng thời tại kho dữ liệu. Hai yêu cầu đã qua validation vẫn có thể xung đột khi thực hiện.

Muốn quy trình nhập có tính nguyên tử, cần đặt ranh giới transaction ở nơi phù hợp và xác minh store hỗ trợ các thao tác cần bao phủ.

### 12.3. Không retry mù quáng cùng collection sau lỗi

Sau exception, cần biết:

- Có phần dữ liệu nào đã commit hay chưa.
- Các đối tượng Java đã nhận ID hoặc version nào.
- Transaction hiện tại còn có thể sử dụng không.
- Việc thử lại có tạo bản ghi trùng hoặc lặp hiệu ứng nghiệp vụ không.

Bắt exception rồi gọi lại saveAll ngay trên cùng collection không tự giải quyết các vấn đề đó.

Nếu quy trình cần retry, hãy thiết kế khóa tương quan, kiểm tra trạng thái và cơ chế idempotency theo yêu cầu nhập. Không coi saveAll là API tự động chống lặp.

## 13. Ghép một phương thức service sử dụng kết quả đúng cách

Giả định:

- ProductRepository là repository của store đã cấu hình, với hợp đồng lưu tương ứng.
- Service được inject biến `products`.
- Hai helper materialize và ensureUniqueSku được đặt trong service hoặc utility phù hợp.
- Quy tắc SKU ổn định và duy nhất trong lô đã được chọn.

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public List<Product> importProducts(
        Iterable<Product> source
) {
    List<Product> input = materialize(source);
    ensureUniqueSku(input);

    Iterable<Product> saved = products.saveAll(input);

    List<Product> result = new ArrayList<>();
    saved.forEach(result::add);

    return result;
}
```

Đây là phương thức bên trong một Spring service, không phải một tệp Java độc lập.

Ranh giới transaction chỉ có tác dụng như mong muốn khi phương thức được gọi qua cơ chế transaction của Spring với transaction manager phù hợp. Annotation không tự cung cấp khả năng transaction cho một store không có khả năng đó.

Ví dụ thực hiện ba việc riêng:

1. Chốt và kiểm tra collection nguồn hữu hạn.
2. Yêu cầu store lưu các đối tượng.
3. Trả các đối tượng nhận được từ repository, qua một List do service tạo.

List kết quả không cam kết thứ tự theo input. Nếu API bên ngoài cần thứ tự request, dựng kết quả theo khóa ổn định như phần trước.

Phương thức cũng không nhận là đã có toàn bộ giá trị trigger hoặc default từ database. Những trường cần thiết phải được đối chiếu theo mapping và đường lưu.

## 14. Bài thực hành có dữ liệu đối chiếu

### 14.1. Chuẩn bị ba sản phẩm

| SKU | Tên | Giá VND |
| --- | --- | ---: |
| KEY-001 | Bàn phím cơ | 1.200.000 |
| MOU-001 | Chuột không dây | 450.000 |
| HUB-001 | Bộ chia USB | 450.000 |

Chọn một store, mapping định danh và repository cụ thể. Trong môi trường test riêng, tạo ba đối tượng mới và truyền bằng một List không chứa null.

### 14.2. Lần lưu thành công

Sau khi gọi saveAll:

- Thu thập kết quả nếu hợp đồng trả Iterable.
- Kiểm tra số phần tử kết quả là 3.
- Ghép theo SKU, không ghép theo chỉ số.
- Kiểm tra tên và giá tương ứng.
- Kiểm tra ID/version nếu mapping và đường lưu đã cam kết có chúng tại thời điểm này.
- Đọc lại theo cách phù hợp để kiểm tra dữ liệu lưu, phân biệt với việc chỉ quan sát instance còn nằm trong bộ nhớ.

Ở JPA, nếu mục tiêu là quan sát dữ liệu trong cơ sở dữ liệu thay vì chỉ entity trong persistence context, cần chủ động thiết kế bước flush/clear hoặc một lần đọc ở ranh giới phù hợp.

Đừng nhầm việc đọc lại trong cùng transaction với bằng chứng một transaction khác đã nhìn thấy dữ liệu commit.

### 14.3. Các biến thể đầu vào

| Trường hợp | Kết quả cần hiểu |
| --- | --- |
| List rỗng | Kết quả thành công rỗng |
| Collection là null | Vi phạm hợp đồng đối số |
| List chứa một phần tử null | Vi phạm hợp đồng phần tử; không suy trạng thái commit chỉ từ lỗi |
| List.of với phần tử null | Lỗi có thể xảy ra ngay khi tạo List |
| Cùng instance xuất hiện hai lần | Hai phần tử đầu vào không có nghĩa hai bản ghi mới |
| Hai instance cùng ID | Cần quy tắc xung đột và cơ chế store; không giả định đối tượng sau thắng |
| HashSet | Kiểm tra số phần tử sau equals/hashCode, trước khi gọi saveAll |
| Iterable chỉ duyệt một lần | Không dựa vào giả định implementation chỉ duyệt đúng một lần |

### 14.4. Quan sát kết quả ở JPA

Nếu môi trường là JPA, có thể thử một đối tượng detached để quan sát sự khác nhau giữa instance đầu vào và instance trả về khi đường lưu sử dụng merge.

Mục tiêu là thấy rằng cùng định danh không đồng nghĩa cùng tham chiếu Java. Không viết logic nghiệp vụ dựa vào yêu cầu hai tham chiếu phải giống nhau.

Quan sát log với lô vừa tạo mới vừa cập nhật để phân biệt:

- Số phần tử đầu vào.
- Số phần tử trả về.
- Số entity hoặc bản ghi phân biệt.
- Số insert, update và truy vấn bổ sung thực tế.

Bốn con số này phục vụ những câu hỏi khác nhau và không bắt buộc trùng nhau.

## 15. Câu hỏi tự kiểm tra

**saveAll có yêu cầu đầu vào phải là List không?**

Không. Hợp đồng nhận Iterable. List, Set và nguồn Iterable phù hợp đều có thể được truyền, nhưng phải xét null, tính hữu hạn và khả năng duyệt.

**Có thể bỏ kết quả rồi luôn dùng collection ban đầu không?**

Không nên mặc định như vậy. Đối tượng trả về có thể khác instance ban đầu và chứa trạng thái cần dùng tiếp sau lưu.

**Kết quả có ba phần tử có nghĩa đã insert ba bản ghi không?**

Không. Nó biểu đạt số phần tử kết quả của lời gọi thành công, không phải một báo cáo số insert.

**Kết quả là List thì có ghép được theo chỉ số không?**

Chỉ khi hợp đồng cụ thể có bảo đảm tương ứng cần thiết. Không suy ra bảo đảm đó chỉ từ việc có kiểu List.

**saveAll có bảo đảm một lần ghi vật lý hoặc một transaction nguyên tử không?**

Không chỉ từ hợp đồng Commons. Cần xem store, implementation, provider/driver và cấu hình transaction.

**Nếu có lỗi thì có thể coi tất cả đã rollback không?**

Không tự kết luận. Phải xác định ranh giới transaction, khả năng store và trạng thái commit thực tế.

## 16. Điều cần nhớ khi áp dụng vào CRUD chung

Xem collection đầu vào là nguồn các đối tượng cần lưu, và xem kết quả trả về là nguồn các đối tượng để xử lý tiếp theo hợp đồng sau lưu.

Kiểm tra đầu vào hữu hạn và khác null, giữ quan hệ generic đúng, dùng khóa ổn định khi cần ghép kết quả, rồi đối chiếu mapping, batching và transaction theo store đang chọn.

Cách sử dụng này giúp saveAll giữ đúng vai trò trong Spring Data Commons: một hợp đồng lưu nhiều đối tượng, với phần thực thi cụ thể do các tầng truy cập dữ liệu tương ứng đảm nhiệm.

