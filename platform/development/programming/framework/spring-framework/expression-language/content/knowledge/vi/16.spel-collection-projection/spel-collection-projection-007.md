# Null-safe projection ?.! trong SpEL

Spring Expression Language (SpEL) hỗ trợ projection để biến đổi từng phần tử trong collection, array hoặc map thành một collection kết quả. Projection thông thường dùng cú pháp `.![expression]`. Khi target có thể là null, **null-safe projection** dùng cú pháp `?.![expression]` để trả về null thay vì gây lỗi khi bắt đầu projection trên target null.

Null-safe projection hữu ích khi dữ liệu tùy chọn, ví dụ một danh sách có thể chưa được tải, một quan hệ có thể chưa tồn tại hoặc một property collection có thể null. Cần phân biệt target collection null với collection rỗng và với phần tử null bên trong collection: ba trường hợp này có hành vi khác nhau.

## 1. Projection thông thường

Projection áp dụng một expression lên từng phần tử của collection. Kết quả là một collection mới chứa các giá trị được tính từ từng phần tử.

Ví dụ, với danh sách khách hàng:

    #customers.![name]

SpEL đọc property `name` của từng customer và tạo danh sách tên. Nếu mỗi customer có property `address`, có thể lấy thành phố:

    #customers.![address.city]

Trong projection, `#this` đại diện cho phần tử hiện tại đang được xử lý. Vì vậy biểu thức trên cũng có thể viết:

    #customers.![#this.address.city]

Dùng `#this` khi predicate hoặc expression phức tạp và cần làm rõ đối tượng hiện tại. Với property đơn giản, tên property trực tiếp thường dễ đọc hơn.

Projection khác selection:

- `.![expression]` biến đổi từng phần tử và tạo collection kết quả.
- `.?[condition]` lọc collection, chỉ giữ lại các phần tử thỏa điều kiện.

Ví dụ, `#customers.![name]` trả về tên của tất cả khách hàng; `#customers.?[active]` trả về các khách hàng đang active.

## 2. Cú pháp null-safe projection

Cú pháp null-safe projection:

    target?.![projectionExpression]

Ví dụ:

    #customers?.![name]

Nếu `#customers` là collection, SpEL thực hiện projection như bình thường. Nếu `#customers` là null, SpEL trả về null cho biểu thức này thay vì cố thực hiện projection trên một target null.

Null-safe projection được hỗ trợ từ **Spring Framework 6.2**. Nếu ứng dụng dùng phiên bản cũ hơn, parser không nhận cú pháp `?.!`; cần dùng điều kiện kiểm tra null tường minh hoặc nâng cấp phiên bản phù hợp.

Ví dụ dùng null guard tương thích với cú pháp projection thông thường:

    #customers == null ? null : #customers.![name]

Cách này kiểm tra collection trước rồi mới thực hiện projection. Nếu collection có thể null và biểu thức cần chạy trên nhiều phiên bản Spring, đây là một phương án thay thế dễ hiểu.

## 3. Phân biệt collection null và collection rỗng

Null-safe projection chỉ thay đổi hành vi khi **target là null**. Một collection rỗng vẫn là một collection hợp lệ; projection trên collection rỗng trả về collection kết quả rỗng.

| Giá trị của target | Biểu thức | Kết quả |
|---|---|---|
| Collection có phần tử | `#items?.![name]` | List các giá trị name |
| Collection rỗng | `#items?.![name]` | List rỗng |
| Collection null | `#items?.![name]` | null |

Sự khác biệt này quan trọng khi kết quả được dùng tiếp. Nếu ứng dụng muốn quy ước “không có dữ liệu” luôn là list rỗng, hãy chuyển null thành collection rỗng một cách tường minh:

    #items == null ? {} : #items.![name]

Trong SpEL, `{}` là inline list rỗng. Biểu thức trên trả về list rỗng khi target null và list được projection khi target có giá trị. Chọn quy ước null hay empty list theo hợp đồng dữ liệu của ứng dụng; hai giá trị này không giống nhau trong mọi API.

## 4. Projection trên property collection có thể null

Một trường hợp phổ biến là collection nằm trong property của object:

    #order?.items?.![productName]

Ở đây có hai điểm có thể null:

1. `#order` có thể null, nên dùng safe navigation trước `items`.
2. `items` có thể null, nên dùng null-safe projection trước `![...]`.

Nếu chỉ viết:

    #order?.items.![productName]

thì safe navigation bảo vệ việc truy cập `items` trên order null, nhưng collection `items` vẫn có thể null khi order tồn tại. Khi đó projection thông thường vẫn có thể lỗi. Hãy đặt null-safe operator tại từng target có thể null.

Ví dụ đầy đủ:

    #order?.items?.![productName]

Nếu kết quả projection còn được dùng để gọi method hoặc truy cập phần tử, hãy xem xét null ở bước tiếp theo:

    #order?.items?.![productName]?.size()

Null-safe projection trả null khi items null. Null-safe method invocation ở cuối giúp tránh gọi `size()` trên kết quả null. Nếu phiên bản SpEL hoặc cú pháp của biểu thức không hỗ trợ cách nối bạn cần, hãy tách thành các bước hoặc dùng toán tử điều kiện.

## 5. Phần tử null bên trong collection

Null-safe projection bảo vệ **collection target**, không tự động bảo vệ mọi phần tử hoặc property lồng nhau. Ví dụ collection có thể tồn tại nhưng chứa một phần tử null:

    #customers?.![name]

Nếu một phần tử là null, truy cập `name` trên phần tử đó vẫn có thể gây lỗi. Khi phần tử hiện tại có thể null, dùng safe navigation trong projection expression:

    #customers?.![#this?.name]

Nếu property trung gian cũng có thể null, tiếp tục dùng safe navigation trên đường dẫn đó:

    #customers?.![#this?.address?.city]

Biểu thức này trả về một kết quả cho mỗi phần tử nguồn; phần tử null hoặc address null tạo ra giá trị null tương ứng trong danh sách kết quả. Projection không tự lọc bỏ các kết quả null.

Nếu muốn loại bỏ các phần tử null hoặc các phần tử thiếu address, hãy kết hợp selection và projection:

    #customers?.?[#this != null and address != null]
             .![address.city]

Selection lọc trước, sau đó projection lấy city. Nếu collection có thể null ở mỗi bước, hãy dùng null-safe operator phù hợp cho từng target có thể null hoặc tách biểu thức bằng null guard rõ ràng.

## 6. Null-safe projection trên Map

Projection cũng hỗ trợ Map. Khi projection trên Map, expression được đánh giá trên từng entry; có thể truy cập key và value của entry hiện tại bằng các tên `key` và `value`.

Ví dụ:

    #scores?.![value]

Biểu thức lấy các value của Map và tạo một List kết quả. Nếu muốn lấy tên hoặc thuộc tính từ object được lưu làm value:

    #profiles?.![value?.displayName]

Nếu Map là null, null-safe projection trả về null. Nếu Map rỗng, kết quả là List rỗng. Nếu value của một entry là null, safe navigation `value?.displayName` giúp kết quả entry đó là null thay vì lỗi khi đọc property.

Muốn tạo kết quả gắn với key, có thể project thành object hoặc cấu trúc mà ứng dụng định nghĩa, hoặc xử lý Map trong Java nếu cần giữ chính xác quan hệ key-value. Projection trên Map tạo danh sách kết quả theo thứ tự iteration của Map; hãy dùng Map có thứ tự xác định nếu thứ tự kết quả có ý nghĩa.

## 7. Null-safe projection trên array

Projection có thể áp dụng cho array. Với array có thể null:

    #names?.![#this?.toUpperCase()]

Nếu array không null, SpEL áp dụng expression lên từng phần tử và tạo collection kết quả. Nếu array null, biểu thức trả về null.

Ví dụ, với array tên:

    String[] names = {"Lan", null, "Minh"};

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("names", names);

    ExpressionParser parser = new SpelExpressionParser();

    List<?> upperNames = parser.parseExpression(
            "#names?.![#this?.toUpperCase()]"
    ).getValue(context, List.class);

Kết quả gồm `"LAN"`, null và `"MINH"`. Safe navigation trên `#this` xử lý phần tử null; `?.!` xử lý trường hợp toàn bộ array null.

## 8. Hỗ trợ theo phiên bản Spring

Null-safe navigation cho property và method đã có từ các phiên bản Spring trước, với cú pháp `?.`. Các toán tử null-safe cho index, selection và projection được bổ sung trong Spring Framework 6.2.

Một số cú pháp liên quan:

| Thao tác | Cú pháp null-safe |
|---|---|
| Property hoặc method | `target?.property`, `target?.method()` |
| Index | `target?.[index]` |
| Selection tất cả | `target?.?[condition]` |
| First selection | `target?.^[condition]` |
| Last selection | `target?.$[condition]` |
| Projection | `target?.![expression]` |

Nếu biểu thức có cú pháp mới nhưng ứng dụng chạy Spring cũ, lỗi có thể xảy ra ngay khi parse chứ không phải khi đánh giá. Hãy xác nhận phiên bản Spring Framework thực tế của ứng dụng trước khi sử dụng các toán tử này.

## 9. Ví dụ đầy đủ với EvaluationContext

Ví dụ sau minh họa collection null, phần tử null và property lồng nhau:

    public class Customer {
        private Address address;

        public Address getAddress() {
            return address;
        }
    }

    public class Address {
        private String city;

        public String getCity() {
            return city;
        }
    }

    List<Customer> customers = loadCustomersOrNull();

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("customers", customers);

    ExpressionParser parser = new SpelExpressionParser();

    Expression citiesExpression = parser.parseExpression(
            "#customers?.![#this?.address?.city]"
    );

    List<?> cities = citiesExpression.getValue(context, List.class);

Nếu `customers` null, kết quả là null. Nếu list rỗng, kết quả là list rỗng. Nếu một customer null hoặc address null, vị trí tương ứng trong kết quả là null. Cách xử lý này giữ nguyên số phần tử đầu vào trong kết quả projection.

Nếu ứng dụng cần loại bỏ những khách hàng chưa có địa chỉ, hãy lọc trước:

    #customers?.?[
        #this != null and address != null
    ]?.![address.city]

Ví dụ này dùng null-safe selection để xử lý collection null, lọc các phần tử có customer và address, rồi projection city. Cú pháp null-safe selection và projection yêu cầu Spring Framework 6.2 trở lên.

## 10. Lỗi thường gặp

- **Dùng `?.!` trên Spring cũ:** cú pháp null-safe projection cần Spring Framework 6.2+; kiểm tra version nếu parser báo lỗi.
- **Chỉ bảo vệ collection:** `#items?.![address.city]` không tự bảo vệ phần tử null hoặc address null; dùng `#this?.address?.city` nếu các giá trị đó có thể thiếu.
- **Nhầm null với collection rỗng:** target null trả null, collection rỗng tạo kết quả rỗng.
- **Cho rằng projection tự lọc null:** projection giữ kết quả null nếu expression của một phần tử trả null; dùng selection nếu muốn loại bỏ phần tử.
- **Nối tiếp thao tác không null-safe:** nếu projection trả null, gọi method hoặc index thông thường trên kết quả có thể gây lỗi; tiếp tục kiểm tra hoặc dùng safe navigation.
- **Quên thứ tự collection:** kết quả projection giữ thứ tự iteration của nguồn; Map không có thứ tự ổn định thì kết quả cũng không nên được coi là ổn định.
- **Dùng projection thay cho lọc:** dùng `.![...]` để biến đổi phần tử, `.?[...]` để chọn phần tử thỏa điều kiện.

## 11. Ghi nhớ

Null-safe projection dùng cú pháp `target?.![expression]` và được hỗ trợ từ Spring Framework 6.2. Nếu target collection hoặc array null, biểu thức trả về null; nếu target rỗng, projection trả về collection rỗng. Toán tử này không tự xử lý phần tử null hoặc property lồng nhau có thể null, vì vậy hãy dùng safe navigation trong expression của projection khi cần. Projection tạo kết quả cho từng phần tử; selection mới là công cụ để lọc. Khi nối thêm method, index hoặc projection khác, hãy kiểm tra null ở từng bước để biểu thức có hành vi rõ ràng.
