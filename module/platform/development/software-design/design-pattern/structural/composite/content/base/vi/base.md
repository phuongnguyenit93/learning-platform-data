# Software Design Design Pattern Structural Composite

Composite là mẫu thiết kế cấu trúc giúp tổ chức các đối tượng thành một cây gồm phần tử đơn (Leaf) và nhóm đối tượng (Composite), đồng thời cho phép chương trình xử lý cả hai qua cùng một hợp đồng Component. Mẫu này phù hợp với cây thư mục, thành phần giao diện, menu phân cấp hoặc nhóm sản phẩm, nơi thao tác trên một nhóm có thể được phân phối đệ quy xuống các phần tử bên trong.

Module dành cho người đã nắm Java hướng đối tượng, interface, đa hình và collection cơ bản. Lộ trình đi từ nhận diện cấu trúc cây đến thiết kế Component, triển khai Leaf và Composite chứa danh sách con, xử lý đệ quy, sử dụng một API thống nhất ở client và duy trì tính hợp lệ của cây khi thêm hoặc xóa phần tử.

Sau khi hoàn thành, bạn có thể xây dựng một cấu trúc đối tượng lồng nhau, thực thi thao tác chung ở mọi cấp và kiểm thử các trường hợp nút lá, nhóm rỗng, cây nhiều cấp và tham chiếu vòng. Bạn cũng sẽ hiểu giới hạn của Composite và phân biệt nó với Decorator hoặc Iterator để lựa chọn đúng trong thiết kế phần mềm.