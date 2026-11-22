# Biên dịch nhiều tệp Java có package và phụ thuộc giữa các lớp

Trong một chương trình Java nhỏ, toàn bộ mã nguồn có thể nằm trong một tệp. Khi chương trình lớn dần, ta thường tách các lớp theo trách nhiệm và đặt chúng vào những package riêng. Khi đó, một lớp có thể sử dụng lớp được khai báo trong tệp khác hoặc package khác. Quá trình biên dịch cần nhận diện được tất cả các mã nguồn liên quan, tìm được các lớp phụ thuộc và đặt các tệp bytecode vào đúng cấu trúc thư mục.

Bài học này trình bày cách tổ chức mã nguồn, biên dịch nhiều tệp bằng **javac**, sử dụng **classpath** và **sourcepath**, chạy lớp có package, cùng cách xử lý những lỗi thường gặp.

## 1. Phân biệt mã nguồn, package và bytecode

Java thường trải qua hai bước riêng:

1. **Biên dịch:** trình biên dịch **javac** đọc các tệp **.java**, kiểm tra cú pháp và kiểu dữ liệu, giải quyết các tham chiếu giữa lớp, rồi tạo các tệp bytecode **.class**.
2. **Chạy chương trình:** lệnh **java** khởi chạy JVM, nạp lớp chính và các lớp mà chương trình cần từ classpath.

Package là tên không gian chứa lớp. Package giúp tổ chức lớp, tránh xung đột tên và thể hiện cấu trúc của chương trình. Ví dụ, khai báo:

    package com.example.model;

cho biết lớp thuộc package **com.example.model**. Khi tổ chức dự án theo quy ước thông dụng, tên package được ánh xạ thành thư mục con dưới thư mục gốc mã nguồn:

    src/
      com/
        example/
          model/
            Product.java

Vì vậy, **src** là thư mục gốc mã nguồn trong ví dụ này; đường dẫn package bắt đầu từ **src**. Tên package và tên thư mục cần thống nhất về chữ hoa, chữ thường, đặc biệt khi dự án được biên dịch trên hệ điều hành phân biệt chữ hoa, chữ thường.

Mỗi tệp nguồn thông thường chứa một lớp **public** cấp cao nhất và tên tệp phải trùng với tên lớp đó. Chẳng hạn, lớp **public class Product** nằm trong **Product.java**.

## 2. Ví dụ về dự án có nhiều lớp phụ thuộc nhau

Giả sử chương trình quản lý một sản phẩm. Ta chia chương trình thành ba phần:

- **Product** lưu thông tin sản phẩm.
- **ProductService** xử lý thông tin của một sản phẩm.
- **Main** tạo đối tượng, gọi dịch vụ và in kết quả.

Cấu trúc thư mục:

    product-app/
      src/
        com/
          example/
            model/
              Product.java
            service/
              ProductService.java
            app/
              Main.java
      out/

Thư mục **src** chứa mã nguồn. Thư mục **out** là nơi lưu các tệp **.class** sau khi biên dịch. Ta tạo **out** trước khi gọi **javac**.

### Tệp Product.java

Đường dẫn: **src/com/example/model/Product.java**

    package com.example.model;

    public class Product {
        private final String name;
        private final double price;

        public Product(String name, double price) {
            this.name = name;
            this.price = price;
        }

        public String getName() {
            return name;
        }

        public double getPrice() {
            return price;
        }
    }

Lớp **Product** thuộc package **com.example.model**. Hai thuộc tính được khai báo **private**; các lớp khác đọc giá trị thông qua getter.

### Tệp ProductService.java

Đường dẫn: **src/com/example/service/ProductService.java**

    package com.example.service;

    import com.example.model.Product;

    public class ProductService {
        public String describe(Product product) {
            return product.getName() + " costs " + product.getPrice();
        }
    }

Lớp **ProductService** thuộc package **com.example.service**. Dòng **import** cho phép sử dụng tên đơn giản **Product** thay vì phải viết tên đầy đủ **com.example.model.Product** ở mọi vị trí. Import chỉ giúp trình biên dịch xác định kiểu được tham chiếu; bản thân dòng import không biên dịch hay đóng gói lớp đó.

### Tệp Main.java

Đường dẫn: **src/com/example/app/Main.java**

    package com.example.app;

    import com.example.model.Product;
    import com.example.service.ProductService;

    public class Main {
        public static void main(String[] args) {
            Product product = new Product("Notebook", 4.5);
            ProductService service = new ProductService();

            System.out.println(service.describe(product));
        }
    }

Lớp **Main** phụ thuộc vào cả **Product** và **ProductService**. Lớp **ProductService** cũng phụ thuộc vào **Product**. Có thể biểu diễn quan hệ này như sau:

    Main
      |----> Product
      |
      +----> ProductService ----> Product

Mũi tên thể hiện lớp ở bên trái cần biết kiểu hoặc sử dụng lớp ở bên phải. Trình biên dịch phải tìm được định nghĩa của những kiểu này để kiểm tra chương trình.

## 3. Biên dịch tất cả tệp nguồn trong một lệnh

Khi có một số ít tệp, cách dễ hiểu nhất là truyền tất cả đường dẫn nguồn cho **javac**. Mở terminal tại thư mục gốc **product-app**, tạo thư mục đầu ra, rồi chạy:

    mkdir out
    javac -d out src/com/example/model/Product.java src/com/example/service/ProductService.java src/com/example/app/Main.java

Nếu thư mục **out** đã tồn tại, bỏ qua lệnh tạo thư mục. Tùy hệ điều hành và shell, lệnh tạo thư mục có thể khác; điều quan trọng là thư mục đích đã tồn tại trước khi biên dịch.

Trong lệnh **javac**:

- **-d out** chỉ định thư mục đích để lưu các tệp **.class**.
- Các đường dẫn **.java** liệt kê những mã nguồn cần biên dịch.
- Trình biên dịch phân tích các khai báo package và tham chiếu kiểu giữa những tệp được cung cấp.

Không cần sắp xếp các tệp theo thứ tự phụ thuộc khi truyền đầy đủ chúng trong cùng một lần gọi **javac**. Ví dụ trên có thể liệt kê **Main.java** trước **Product.java**; trình biên dịch vẫn có thể giải quyết các kiểu vì cả ba mã nguồn đều được đưa vào cùng lượt biên dịch.

Sau khi biên dịch thành công, cấu trúc đầu ra có dạng:

    out/
      com/
        example/
          model/
            Product.class
          service/
            ProductService.class
          app/
            Main.class

**javac** tạo thư mục package bên dưới **out** dựa trên khai báo package. Thư mục **out** là gốc của cây package đã biên dịch.

## 4. Chạy lớp chính có package

Từ thư mục gốc **product-app**, chạy:

    java -cp out com.example.app.Main

Trong lệnh này:

- **-cp out** (viết đầy đủ là **-classpath out**) cho JVM biết nơi tìm các lớp đã biên dịch.
- **out** phải là thư mục gốc chứa thư mục **com**, không phải thư mục **out/com/example/app**.
- **com.example.app.Main** là tên lớp đầy đủ (fully qualified class name), gồm package và tên lớp.
- Không thêm phần mở rộng **.class** vào tên lớp khi chạy bằng **java**.

Kết quả:

    Notebook costs 4.5

Nếu chạy lệnh từ một thư mục khác, cần điều chỉnh đường dẫn classpath và đường dẫn nguồn tương ứng. Các đường dẫn tương đối luôn được tính từ thư mục làm việc hiện tại của terminal.

## 5. Biên dịch theo từng giai đoạn

Trong một số quy trình, các lớp được biên dịch ở những thời điểm khác nhau. Khi đó, lớp phụ thuộc phải có sẵn dưới dạng **.class** hoặc mã nguồn mà trình biên dịch có thể tìm thấy.

Vẫn đứng tại thư mục gốc dự án và bảo đảm **out** đã tồn tại, thực hiện lần lượt:

    javac -d out src/com/example/model/Product.java
    javac -cp out -d out src/com/example/service/ProductService.java
    javac -cp out -d out src/com/example/app/Main.java

Lệnh đầu tiên tạo **Product.class**. Lệnh thứ hai dùng **-cp out** để tìm **Product.class** khi biên dịch **ProductService**. Lệnh thứ ba cũng dùng **-cp out** để tìm cả **Product.class** và **ProductService.class**.

Ở đây, hai tùy chọn có vai trò khác nhau:

- **-d out** quy định nơi ghi các lớp vừa biên dịch.
- **-cp out** quy định nơi tìm các lớp đã biên dịch cần thiết cho lần biên dịch hiện tại.

Nếu bỏ **-cp out** ở lệnh thứ hai hoặc thứ ba, **javac** có thể không tìm thấy các lớp đã tạo trong thư mục **out**, vì thư mục này không tự động trở thành classpath chỉ nhờ được dùng làm thư mục đầu ra.

Sau khi hoàn tất ba lệnh, chạy chương trình bằng cùng classpath:

    java -cp out com.example.app.Main

Biên dịch theo từng giai đoạn hữu ích khi dự án có các phần độc lập hoặc khi một thư viện đã được biên dịch trước. Với dự án nhỏ, biên dịch toàn bộ tệp nguồn trong một lệnh thường đơn giản hơn.

## 6. Dùng sourcepath để tìm mã nguồn phụ thuộc

Nếu muốn chỉ định một tệp nguồn bắt đầu, có thể dùng **-sourcepath** để cho **javac** biết nơi tìm những tệp **.java** khác mà tệp đó tham chiếu.

Với cấu trúc dự án ở trên, lệnh sau có thể biên dịch **Main** cùng những mã nguồn phụ thuộc mà trình biên dịch tìm thấy dưới **src**:

    javac -d out -sourcepath src src/com/example/app/Main.java

Khi **Main** tham chiếu **Product** và **ProductService**, trình biên dịch tìm các tệp nguồn tương ứng theo package bên dưới thư mục **src**. Nếu **ProductService** tiếp tục tham chiếu **Product**, trình biên dịch cũng có thể tìm và biên dịch mã nguồn của **Product**.

**-sourcepath** là nơi tìm **mã nguồn**; **-cp** là nơi tìm **lớp đã biên dịch và thư viện**. Hai tùy chọn này giải quyết hai loại đầu vào khác nhau. Có thể chỉ định cả hai khi dự án cần tìm mã nguồn và các thư viện đã biên dịch.

Cách dùng sourcepath phụ thuộc vào việc cấu trúc thư mục có khớp với tên package hay không. Với quy ước thông dụng, thư mục gốc sourcepath là **src**, còn package **com.example.model** nằm trong **src/com/example/model**.

## 7. Các tùy chọn javac thường dùng

| Tùy chọn | Công dụng |
| --- | --- |
| **-d <thư_mục>** | Ghi các tệp **.class** vào thư mục đích theo cấu trúc package. |
| **-cp <đường_dẫn>** | Tìm lớp đã biên dịch và thư viện cần thiết. Có thể dùng **-classpath**. |
| **-sourcepath <đường_dẫn>** | Tìm tệp **.java** phụ thuộc khi biên dịch. |
| **-encoding UTF-8** | Chỉ định bảng mã của tệp nguồn. Hữu ích khi mã nguồn có ký tự tiếng Việt. |
| **-Xlint:all** | Yêu cầu trình biên dịch hiển thị thêm nhiều cảnh báo. |

Ví dụ, nếu mã nguồn có ký tự tiếng Việt và cần xem cảnh báo:

    javac -encoding UTF-8 -Xlint:all -d out src/com/example/model/Product.java src/com/example/service/ProductService.java src/com/example/app/Main.java

Classpath có thể chứa nhiều mục. Trên Windows, các mục thường được phân tách bằng dấu chấm phẩy (**;**); trên Linux và macOS, thường dùng dấu hai chấm (**:**). Ví dụ:

    java -cp "out;lib/example.jar" com.example.app.Main

    java -cp "out:lib/example.jar" com.example.app.Main

Hai dòng trên minh họa cú pháp classpath trên hai nhóm hệ điều hành khác nhau. Khi dùng shell cụ thể, cần giữ đúng ký tự phân tách của hệ điều hành đó.

## 8. Những lỗi thường gặp và cách xử lý

### Lỗi package không tồn tại

Thông báo có thể chứa nội dung **package ... does not exist**. Nguyên nhân thường là thiếu tệp nguồn trong lệnh biên dịch, sai khai báo import, sai tên package, hoặc classpath/sourcepath không trỏ tới đúng thư mục gốc.

Cách kiểm tra:

1. Đọc dòng **package** ở đầu tệp đang được tham chiếu.
2. Kiểm tra tệp nguồn có nằm dưới thư mục gốc sourcepath theo đúng đường dẫn package không.
3. Nếu lớp đã biên dịch, kiểm tra classpath có chứa thư mục gốc của cây package không.
4. Nếu biên dịch nhiều tệp cùng lúc, kiểm tra danh sách đối số có bao gồm các tệp cần thiết không.

### Lỗi cannot find symbol

Lỗi **cannot find symbol** nghĩa là trình biên dịch không xác định được tên lớp, phương thức hoặc biến tại vị trí sử dụng. Với lỗi liên quan đến lớp khác, hãy kiểm tra import, cách viết tên, package và việc lớp phụ thuộc đã được đưa vào lượt biên dịch hoặc classpath hay chưa.

### Lỗi tên tệp không khớp tên lớp public

Nếu khai báo **public class Product**, tên tệp phải là **Product.java**. Java phân biệt chữ hoa, chữ thường trong tên lớp và tên tệp trên nhiều hệ thống tệp.

### Lỗi Could not find or load main class

Lỗi này xuất hiện khi JVM không tìm thấy lớp được yêu cầu. Hãy kiểm tra:

- Classpath có trỏ tới thư mục gốc chứa cây package đã biên dịch hay không.
- Tên lớp có đầy đủ package, ví dụ **com.example.app.Main**, hay không.
- Lớp **Main.class** đã được tạo đúng vị trí **out/com/example/app/Main.class** hay chưa.
- Tên package có khớp chính xác chữ hoa và chữ thường hay không.

### Lỗi NoClassDefFoundError khi chương trình đang chạy

Lỗi này thường cho biết JVM đã bắt đầu chạy nhưng không nạp được một lớp cần thiết. Một lớp có thể đã có trong lúc biên dịch nhưng thiếu ở classpath lúc chạy. Hãy thêm thư mục hoặc tệp JAR chứa lớp đó vào classpath của lệnh **java**.

### Biên dịch được nhưng chạy phiên bản lớp cũ

Nếu thư mục đầu ra còn các tệp **.class** từ lần biên dịch trước, JVM có thể nạp nhầm bytecode cũ khi classpath chứa nhiều thư mục có cùng tên lớp. Kiểm tra thứ tự các mục trong classpath và cân nhắc tạo lại thư mục đầu ra trước một lần build sạch. Chỉ xóa thư mục đầu ra của chính dự án khi chắc chắn đó là thư mục sinh ra dành riêng cho build.

## 9. Liên hệ với công cụ build

Gọi **javac** trực tiếp giúp hiểu rõ các bước mà công cụ build tự động hóa:

- xác định thư mục chứa mã nguồn;
- tìm các lớp và thư viện phụ thuộc;
- biên dịch mã nguồn;
- đặt bytecode vào thư mục đầu ra;
- tạo gói chạy hoặc cấu hình classpath khi khởi chạy.

Khi dự án lớn hơn, Maven hoặc Gradle có thể quản lý các bước này bằng cấu hình build. Các công cụ đó thường áp dụng quy ước thư mục, theo dõi thư viện phụ thuộc và thực hiện biên dịch theo nhiệm vụ. Dù dùng công cụ nào, các khái niệm package, classpath, sourcepath và thư mục đầu ra vẫn giữ nguyên ý nghĩa.

Khi cần tìm lỗi build, hãy xác định lỗi xảy ra ở bước nào: trình biên dịch không tìm thấy mã nguồn, không tìm thấy lớp đã biên dịch, hay JVM không tìm thấy lớp lúc chạy. Phân biệt đúng các trường hợp này giúp chọn đúng nơi cần kiểm tra: danh sách tệp nguồn, khai báo package/import, sourcepath, classpath hoặc thư mục đầu ra.
