# Mô hình dữ liệu bảng từ mảng, danh sách hoặc thuộc tính đối tượng

Spring Shell có API dựng bảng văn bản trong terminal. Phần dữ liệu được mô tả bằng một TableModel, còn TableBuilder quyết định cách hiển thị như đường viền, độ rộng cột, ngắt dòng và căn lề. Nhờ tách dữ liệu khỏi cách trình bày, cùng một nguồn dữ liệu có thể được hiển thị theo nhiều kiểu bảng.

Có ba cách tạo mô hình thường dùng:

- ArrayTableModel nhận mảng hai chiều theo thứ tự hàng trước.
- TableModelBuilder tạo mô hình từng hàng và từng ô, phù hợp khi dữ liệu được thu thập dần từ danh sách.
- BeanListTableModel đọc thuộc tính từ danh sách object, cho phép chọn và sắp xếp các cột theo tên property.

Các ví dụ dùng Spring Shell 3.1.x và đối chiếu API Spring Shell 4.0.4. Khác biệt đáng chú ý khi nâng cấp là package của các lớp table: 3.x dùng org.springframework.shell.table, còn API JLine table trong 4.x dùng org.springframework.shell.jline.tui.table.

## 1. Tách mô hình dữ liệu khỏi cách trình bày

Một bảng có hai phần:

1. **TableModel** cung cấp số hàng, số cột và giá trị tại từng vị trí.
2. **TableBuilder** nhận model rồi cấu hình cách dựng bảng thành chuỗi có thể in ra terminal.

Hợp đồng cơ bản của TableModel gồm ba phương thức:

| Phương thức | Ý nghĩa |
|---|---|
| getRowCount() | Số hàng có thể đọc |
| getColumnCount() | Số cột có thể đọc |
| getValue(row, column) | Giá trị tại hàng và cột được chỉ định |

Chỉ số hàng và cột bắt đầu từ 0. TableModel không bắt buộc dữ liệu phải đến từ mảng hoặc bean; bất kỳ lớp nào cung cấp đúng ba phương thức này đều có thể làm nguồn dữ liệu cho Table.

Luồng tạo bảng thường là:

~~~text
Nguồn dữ liệu
    |
    v
TableModel
    |
    v
TableBuilder + cấu hình
    |
    v
Table.render(width)
    |
    v
Chuỗi kết quả được in ra terminal
~~~

Ví dụ, command có thể trả về chuỗi đã render:

~~~java
return new TableBuilder(model)
        .addHeaderAndVerticalsBorders(BorderStyle.fancy_light)
        .build()
        .render(100);
~~~

Nếu command trả về String, result handler của Spring Shell sẽ hiển thị chuỗi đó. Khi cần kiểm soát output hoặc kết hợp nhiều phần nội dung, có thể render bảng rồi ghi chuỗi qua writer/terminal của mô hình command đang sử dụng.

## 2. Tạo bảng từ mảng hai chiều với ArrayTableModel

ArrayTableModel phù hợp khi dữ liệu đã có sẵn dưới dạng Object[][]. Đây là mô hình theo hàng: mỗi mảng con biểu diễn một hàng, và mỗi phần tử trong mảng con là một ô.

Ví dụ:

~~~java
Object[][] data = {
        {"Mã SKU", "Tên sản phẩm", "Tồn kho"},
        {"SKU-101", "Bàn phím cơ", 12},
        {"SKU-102", "Chuột không dây", 25},
        {"SKU-103", "Màn hình", 7}
};

TableModel model = new ArrayTableModel(data);

Table table = new TableBuilder(model)
        .addHeaderAndVerticalsBorders(BorderStyle.fancy_light)
        .build();

return table.render(100);
~~~

Hàng đầu tiên trong mảng được dùng làm dữ liệu hàng đầu tiên. TableModel không tự suy luận tên cột từ tên biến; vì vậy, nếu muốn có hàng tiêu đề, hãy thêm hàng tiêu đề vào mảng như ví dụ. addHeaderAndVerticalsBorders vẽ đường viền để làm nổi bật hàng đầu tiên và các cột, nhưng không thay đổi cấu trúc dữ liệu.

Kết quả minh họa:

~~~text
┌─────────┬─────────────────┬─────────┐
│ Mã SKU  │ Tên sản phẩm    │ Tồn kho │
├─────────┼─────────────────┼─────────┤
│ SKU-101 │ Bàn phím cơ     │ 12      │
│ SKU-102 │ Chuột không dây │ 25      │
│ SKU-103 │ Màn hình        │ 7       │
└─────────┴─────────────────┴─────────┘
~~~

Giữ số ô của các hàng nhất quán. Nếu một hàng có ít cột hơn hàng đầu tiên, việc truy cập ô có thể không hợp lệ hoặc bảng không hiển thị đúng cấu trúc dự kiến. Với giá trị không có dữ liệu, hãy cân nhắc dùng chuỗi rỗng hoặc một ký hiệu như dấu gạch ngang để người đọc phân biệt với lỗi định dạng.

## 3. Chuyển List thành mảng hai chiều

Nếu dữ liệu ban đầu là danh sách các mảng hàng, có thể chuyển sang Object[][] rồi dùng ArrayTableModel. Cách này hữu ích khi các hàng được tạo trong một vòng xử lý hoặc lấy từ nhiều nguồn trước khi dựng bảng.

~~~java
List<Object[]> rows = new ArrayList<>();

rows.add(new Object[] {"Mã SKU", "Kho", "Số lượng"});
rows.add(new Object[] {"SKU-201", "HN", 10});
rows.add(new Object[] {"SKU-202", "HCM", 18});
rows.add(new Object[] {"SKU-203", "DN", 6});

Object[][] data = rows.toArray(Object[][]::new);
TableModel model = new ArrayTableModel(data);

return new TableBuilder(model)
        .addHeaderAndVerticalsBorders(BorderStyle.fancy_light)
        .build()
        .render(90);
~~~

Với Java 11 trở lên, Object[][]::new là cách gọn để chuyển List<Object[]> thành mảng hai chiều. Nếu dùng Java cũ hơn, có thể dùng rows.toArray(new Object[0][]).

Đừng chuyển một List<Product> thành Object[][] bằng cách đưa nguyên object vào từng ô nếu mục tiêu là hiển thị nhiều thuộc tính. Khi đó, BeanListTableModel thường rõ ràng hơn vì nó biết cách đọc từng property của object.

## 4. Xây dựng mô hình từng hàng với TableModelBuilder

TableModelBuilder phù hợp khi dữ liệu được thêm từng ô hoặc từng hàng. Gọi addRow() để bắt đầu hàng mới, rồi gọi addValue(...) cho từng cột. Cuối cùng gọi build() để tạo TableModel.

~~~java
TableModel model = new TableModelBuilder<Object>()
        .addRow()
            .addValue("Mã đơn")
            .addValue("Khách hàng")
            .addValue("Trạng thái")
        .addRow()
            .addValue("ORD-501")
            .addValue("Nguyễn An")
            .addValue("Đang xử lý")
        .addRow()
            .addValue("ORD-502")
            .addValue("Trần Bình")
            .addValue("Đã giao")
        .build();

return new TableBuilder(model)
        .addHeaderBorder(BorderStyle.fancy_light)
        .build()
        .render(100);
~~~

Builder giúp tránh phải khai báo mảng lớn ngay từ đầu. Mỗi hàng cần có cùng số lượng giá trị; nếu chuyển sang hàng mới khi hàng trước chưa đủ cột hoặc thêm quá nhiều giá trị, builder có thể từ chối cấu trúc không đồng nhất.

TableModelBuilder không tự biết đâu là header. Hãy thêm hàng tiêu đề đầu tiên như ví dụ và chọn kiểu border để phân biệt hàng đó.

## 5. Tạo bảng từ danh sách object với BeanListTableModel

Khi dữ liệu là List<ProductRow>, BeanListTableModel có thể đọc các thuộc tính JavaBean của từng object. Có thể chỉ định property nào được đưa vào bảng và thứ tự của chúng.

Ví dụ lớp dữ liệu:

~~~java
public class ProductRow {

    private final String sku;
    private final String name;
    private final int quantity;

    public ProductRow(String sku, String name, int quantity) {
        this.sku = sku;
        this.name = name;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Tạo danh sách và chọn các property cần hiển thị:

~~~java
List<ProductRow> products = List.of(
        new ProductRow("SKU-301", "Bàn phím cơ", 12),
        new ProductRow("SKU-302", "Chuột không dây", 25),
        new ProductRow("SKU-303", "Màn hình", 7)
);

TableModel model = new BeanListTableModel<>(
        products,
        "sku",
        "name",
        "quantity");
~~~

Danh sách propertyNames quyết định những cột nào được đọc và thứ tự hiển thị. Đây là cách tốt để chỉ công khai các trường cần thiết; không phải mọi thuộc tính của object đều nên xuất hiện trong terminal.

Nếu dùng constructor BeanListTableModel(Class<T>, Iterable<T>), model có thể tự phát hiện các property của bean. Tuy nhiên, với command nghiệp vụ, nên chọn rõ property để thứ tự cột ổn định và tránh vô tình hiển thị trường nội bộ.

## 6. Đặt nhãn cột thân thiện bằng LinkedHashMap

Constructor nhận LinkedHashMap<String, Object> cho phép kết hợp tên property với nhãn cột. Key là tên property cần đọc từ bean; value là nội dung tiêu đề được hiển thị. Dùng LinkedHashMap để giữ thứ tự cột.

~~~java
LinkedHashMap<String, Object> headers = new LinkedHashMap<>();
headers.put("sku", "Mã SKU");
headers.put("name", "Tên sản phẩm");
headers.put("quantity", "Tồn kho");

TableModel model = new BeanListTableModel<>(products, headers);

return new TableBuilder(model)
        .addHeaderAndVerticalsBorders(BorderStyle.fancy_light)
        .build()
        .render(100);
~~~

Constructor này tạo một hàng tiêu đề từ các value của map rồi đọc dữ liệu ở các hàng tiếp theo theo property tương ứng. Vì vậy, không cần chèn thêm một hàng tiêu đề thủ công như khi dùng ArrayTableModel hoặc TableModelBuilder.

Nếu thứ tự cột quan trọng, đừng thay LinkedHashMap bằng HashMap. HashMap không cam kết thứ tự lặp, trong khi header và property cần khớp đúng cột.

## 7. Chọn model phù hợp với nguồn dữ liệu

| Nguồn dữ liệu | Model phù hợp | Cách xác định cột |
|---|---|---|
| Mảng hai chiều Object[][] | ArrayTableModel | Mỗi phần tử của hàng là một ô; thêm header thành hàng đầu tiên |
| List<Object[]> | Chuyển sang Object[][] rồi dùng ArrayTableModel | Thứ tự phần tử trong mỗi mảng |
| Dữ liệu được tạo dần | TableModelBuilder | addRow() và addValue() theo thứ tự |
| List JavaBean | BeanListTableModel | Tên property và thứ tự propertyNames |
| List JavaBean cần nhãn riêng | BeanListTableModel với LinkedHashMap | Key là property, value là nhãn cột |
| Dữ liệu tính toán hoặc nguồn tùy chỉnh | Tự triển khai TableModel | Cài getRowCount(), getColumnCount(), getValue() |

Không có model nào luôn tốt nhất. ArrayTableModel dễ dùng khi dữ liệu đã phẳng và có cấu trúc cố định. BeanListTableModel giúp tránh chuyển object thành mảng thủ công. TableModelBuilder thuận tiện khi xây bảng từng bước. Custom TableModel phù hợp khi dữ liệu cần tính toán theo chỉ số hoặc lấy từ một nguồn không phải collection thông thường.

## 8. Tự triển khai TableModel

Nếu DTO không có JavaBean getter hoặc cần tạo cột dẫn xuất, có thể triển khai TableModel trực tiếp.

~~~java
List<ProductRow> products = productService.findAll();

TableModel model = new TableModel() {

    @Override
    public int getRowCount() {
        return products.size() + 1;
    }

    @Override
    public int getColumnCount() {
        return 3;
    }

    @Override
    public Object getValue(int row, int column) {
        if (row == 0) {
            return switch (column) {
                case 0 -> "Mã SKU";
                case 1 -> "Tên sản phẩm";
                case 2 -> "Tồn kho";
                default -> "";
            };
        }

        ProductRow product = products.get(row - 1);
        return switch (column) {
            case 0 -> product.getSku();
            case 1 -> product.getName();
            case 2 -> product.getQuantity();
            default -> "";
        };
    }
};
~~~

Ở đây hàng 0 là header; các hàng sau ánh xạ sang danh sách products. Cách này giúp tính giá trị từng ô theo nhu cầu mà không cần tạo một bản sao Object[][] của toàn bộ dữ liệu.

Hãy đảm bảo các chỉ số hợp lệ và giá trị trả về có thể được format. getValue() có thể trả null theo hợp đồng API, nhưng cần quyết định cách hiển thị null để bảng không gây hiểu nhầm.

## 9. Cấu hình đường viền và cách render

TableBuilder nhận TableModel và cho phép chọn kiểu đường viền. Một số kiểu thường gặp:

| BorderStyle | Cách hiển thị |
|---|---|
| oldschool | Ký tự ASCII đơn giản như dấu gạch và dấu phân cách |
| fancy_light | Ký tự box-drawing nét mảnh |
| fancy_double | Đường viền kép |
| fancy_heavy | Đường viền đậm |
| air | Không vẽ đường viền, tạo khoảng trống giữa cột |

Các cách cấu hình thường dùng:

~~~java
TableBuilder builder = new TableBuilder(model);

builder.addOutlineBorder(BorderStyle.fancy_light);
builder.addHeaderBorder(BorderStyle.fancy_light);
builder.addHeaderAndVerticalsBorders(BorderStyle.fancy_light);
builder.addFullBorder(BorderStyle.fancy_light);
builder.addInnerBorder(BorderStyle.fancy_light);

Table table = builder.build();
String output = table.render(100);
~~~

Chỉ chọn một kiểu border phù hợp với bố cục mong muốn; đoạn code trên liệt kê các API có thể dùng, không phải cấu hình cần gọi tất cả liên tiếp. addHeaderBorder làm nổi bật hàng đầu và đường viền ngoài. addFullBorder kẻ viền từng ô. addOutlineBorder chỉ kẻ đường viền ngoài.

render(totalAvailableWidth) nhận chiều rộng tối đa có sẵn và trả về String. Hãy chọn chiều rộng phù hợp với terminal; bảng quá rộng có thể xuống dòng hoặc khó đọc trên màn hình nhỏ.

## 10. Căn lề, wrap và format giá trị

TableBuilder mặc định format giá trị bằng toString(), chọn kích thước cột dựa trên không gian có thể dùng, ngắt dòng theo khoảng trắng và căn trái. Cấu hình này phù hợp với bảng đơn giản nhưng có thể chưa đủ cho số tiền, ngày tháng, phần trăm hoặc nội dung dài.

Khi cần trình bày tốt hơn, có thể tùy chỉnh theo CellMatcher:

- Formatter chuyển giá trị thô thành chuỗi hiển thị, ví dụ định dạng tiền theo locale.
- SizeConstraints quyết định giới hạn chiều rộng cột.
- TextWrapper quyết định cách ngắt hoặc cắt nội dung.
- Aligner quyết định căn trái, phải hoặc giữa theo từng ô.
- CellMatcher chọn nhóm ô cần áp dụng các cấu hình trên, chẳng hạn cột số lượng hoặc tất cả ô chứa kiểu Map.

Ví dụ về quyết định định dạng:

| Dữ liệu | Cách hiển thị nên cân nhắc |
|---|---|
| Giá tiền | Định dạng theo locale, có đơn vị tiền tệ |
| Ngày giờ | Chọn mẫu ngày giờ ngắn và thống nhất |
| Số lượng | Căn phải để dễ so sánh |
| Mô tả dài | Wrap hoặc giới hạn độ rộng |
| Giá trị null | Hiển thị dấu gạch ngang hoặc chuỗi rỗng |
| Mã định danh | Giữ nguyên chuỗi, tránh wrap nếu có thể |

Không nên mặc định rằng toString() của mọi kiểu dữ liệu tạo ra nội dung phù hợp cho người dùng. Với kiểu ngày, tiền hoặc object lồng nhau, hãy format rõ ràng trước khi đưa vào model hoặc cấu hình formatter cho cell.

## 11. Xử lý dữ liệu rỗng, null và cột dài

Một số trường hợp cần xử lý trước khi render:

- **Danh sách rỗng:** quyết định hiển thị bảng chỉ có header hay thông báo “Không có dữ liệu”. Với bảng không có dòng dữ liệu, thông báo riêng thường dễ hiểu hơn.
- **Giá trị null:** thay bằng chuỗi có ý nghĩa hoặc cấu hình formatter; không để người dùng phải đoán ô trống có nghĩa gì.
- **Độ dài không đồng nhất:** bảo đảm các hàng có cùng số cột và cùng thứ tự trường.
- **Chuỗi rất dài:** giới hạn chiều rộng hoặc wrap để không làm vỡ bố cục terminal.
- **Nhiều dòng:** kiểm tra cách TextWrapper xử lý newline; có thể cần chuẩn hóa thành một dòng hoặc chủ động wrap.
- **Số lượng bản ghi lớn:** phân trang hoặc giới hạn số hàng trả về thay vì in hàng nghìn dòng cùng lúc.

Nếu dữ liệu đến từ database, nên chọn đúng cột và giới hạn số bản ghi ở truy vấn/service. Đừng tải toàn bộ bảng dữ liệu lớn chỉ để render một trang terminal.

## 12. Khác biệt package khi nâng lên Spring Shell 4.x

Các model vẫn có tên quen thuộc, nhưng API table trong Spring Shell 4.0.4 nằm trong package JLine-specific:

| Spring Shell 3.1.x | Spring Shell 4.0.4 |
|---|---|
| org.springframework.shell.table.TableModel | org.springframework.shell.jline.tui.table.TableModel |
| org.springframework.shell.table.ArrayTableModel | org.springframework.shell.jline.tui.table.ArrayTableModel |
| org.springframework.shell.table.BeanListTableModel | org.springframework.shell.jline.tui.table.BeanListTableModel |
| org.springframework.shell.table.TableModelBuilder | org.springframework.shell.jline.tui.table.TableModelBuilder |
| org.springframework.shell.table.TableBuilder | org.springframework.shell.jline.tui.table.TableBuilder |
| org.springframework.shell.table.BorderStyle | org.springframework.shell.jline.tui.table.BorderStyle |

Ví dụ import trong Spring Shell 3.x:

~~~java
import org.springframework.shell.table.ArrayTableModel;
import org.springframework.shell.table.BorderStyle;
import org.springframework.shell.table.TableBuilder;
import org.springframework.shell.table.TableModel;
~~~

Import trong Spring Shell 4.0.4:

~~~java
import org.springframework.shell.jline.tui.table.ArrayTableModel;
import org.springframework.shell.jline.tui.table.BorderStyle;
import org.springframework.shell.jline.tui.table.TableBuilder;
import org.springframework.shell.jline.tui.table.TableModel;
~~~

Khi nâng cấp, cập nhật package import theo API đang dùng và kiểm tra dependency JLine của ứng dụng. Nếu project chỉ có core module mà không có module cung cấp JLine table API, các import trong package jline.tui.table sẽ không có trên compile classpath.

Không trộn class TableModel của package 3.x với ArrayTableModel hoặc TableBuilder của package 4.x. Dù tên lớp giống nhau, chúng thuộc hai package khác nhau và không thể truyền qua lại như cùng một kiểu Java.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy hàng tiêu đề | Mảng không có hàng header hoặc BeanListTableModel dùng constructor propertyNames | Thêm hàng đầu tiên hoặc dùng constructor LinkedHashMap để tạo header |
| Cột xuất hiện sai thứ tự | Property list hoặc map không giữ thứ tự mong muốn | Truyền propertyNames rõ ràng hoặc dùng LinkedHashMap |
| BeanListTableModel không đọc được cột | Tên property không đúng hoặc object không có JavaBean property tương ứng | Kiểm tra getter và tên property |
| Bảng báo lỗi khi đọc một ô | Các hàng có số cột không đồng nhất hoặc index sai | Kiểm tra kích thước từng hàng và chỉ số row/column |
| Giá trị object hiển thị khó hiểu | Formatter mặc định dùng toString() | Chuyển đổi giá trị trước hoặc cấu hình formatter |
| Bảng quá rộng | Nội dung dài và sizing strategy cấp quá nhiều không gian | Giới hạn width, wrap/crop và chỉ chọn cột cần thiết |
| Bảng không có viền | Chưa cấu hình border hoặc đang dùng BorderStyle.air | Chọn addHeaderBorder, addOutlineBorder hoặc addFullBorder |
| Import table không biên dịch sau khi nâng 4.x | Package đã chuyển sang jline.tui.table | Cập nhật import và kiểm tra dependency JLine |
| Header bị lặp | Đã thêm header trong dữ liệu rồi lại thêm một hàng header ở model bean | Chỉ dùng một cách tạo header |

## 14. Quy trình xây dựng bảng cho command

1. Xác định nguồn dữ liệu: Object[][], List<Object[]>, List<Bean> hay dữ liệu cần tính toán.
2. Chọn ArrayTableModel, TableModelBuilder, BeanListTableModel hoặc tự triển khai TableModel.
3. Quyết định hàng header được tạo trong mảng, trong builder hay bằng LinkedHashMap.
4. Chọn cột hiển thị và thứ tự cột; không đưa trường nhạy cảm hoặc nội bộ vào output.
5. Chuẩn hóa giá trị null, ngày tháng, số tiền và chuỗi dài trước khi render.
6. Dùng TableBuilder để cấu hình border, sizing, wrapping và alignment.
7. Gọi render(width) với chiều rộng terminal hợp lý.
8. Kiểm tra bảng với danh sách rỗng, một dòng, nhiều dòng và giá trị dài.
9. Khi nâng cấp 4.x, đổi package sang org.springframework.shell.jline.tui.table và xác nhận module cần thiết có trên classpath.

## 15. Tổng kết

TableModel là hợp đồng cung cấp dữ liệu theo hàng và cột; TableBuilder quyết định cách dữ liệu được trình bày trong terminal. ArrayTableModel phù hợp với mảng hai chiều hoặc danh sách hàng đã chuyển thành Object[][]. TableModelBuilder giúp thêm dữ liệu từng hàng. BeanListTableModel đọc property từ danh sách JavaBean, cho phép chọn cột và dùng LinkedHashMap để đặt nhãn tiêu đề.

Hãy chọn model theo hình dạng dữ liệu, giữ số cột nhất quán, kiểm soát header và định dạng giá trị trước khi render. Spring Shell 3.1.x dùng package org.springframework.shell.table; API table trong Spring Shell 4.0.4 dùng org.springframework.shell.jline.tui.table. Khi nâng cấp, cập nhật import và kiểm tra dependency JLine cùng các trường hợp dữ liệu rỗng, null và cột dài.

## Tài liệu tham khảo

- [Spring Shell 3.1.x TableModel API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/TableModel.html) — hợp đồng getRowCount, getColumnCount, getValue và transpose.
- [Spring Shell 3.1.x ArrayTableModel API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/ArrayTableModel.html) — model lấy dữ liệu từ mảng hai chiều theo hàng.
- [Spring Shell 3.1.x BeanListTableModel API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/BeanListTableModel.html) — model từ Iterable bean, chọn property và header map.
- [Spring Shell 3.1.x TableModelBuilder API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/TableModelBuilder.html) — tạo model tăng dần bằng addRow và addValue.
- [Spring Shell 3.1.x TableBuilder API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/TableBuilder.html) — cấu hình border và xây Table.
- [Spring Shell 3.1.x Table API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/table/Table.html) — render bảng theo chiều rộng khả dụng.
- [Spring Shell 4.0.4 ArrayTableModel API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/ArrayTableModel.html) — mảng hai chiều trong package JLine table.
- [Spring Shell 4.0.4 BeanListTableModel API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/BeanListTableModel.html) — danh sách bean và property được chọn.
- [Spring Shell 4.0.4 TableModelBuilder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableModelBuilder.html) — xây dựng model từng hàng.
- [Spring Shell 4.0.4 TableBuilder API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/TableBuilder.html) — border, cell matcher và cách dựng bảng.
- [Spring Shell 4.0.3 Table API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/tui/table/Table.html) — formatter, size constraints, wrapping, alignment và render.
