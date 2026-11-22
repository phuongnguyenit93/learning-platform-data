# Geo-shape query và quan hệ hình học

## 1. Geo-shape query giải quyết vấn đề gì?

Trong ứng dụng có dữ liệu địa lý, đôi khi tìm kiếm không chỉ dựa trên một tọa độ. Một document có thể đại diện cho một khu vực giao hàng, ranh giới quận, tuyến đường, vùng phủ sóng hoặc khu đất. Khi người dùng chọn một khu vực trên bản đồ, ứng dụng cần tìm các document có hình học liên quan đến khu vực đó.

Ví dụ:

- Tìm các vùng giao hàng giao với vùng người dùng vẽ trên bản đồ.
- Tìm các quận nằm hoàn toàn bên trong một khu vực được chọn.
- Tìm những khu đất chứa trọn một vùng quy hoạch.
- Loại các vùng không có bất kỳ phần giao nào với khu vực cấm.
- Tìm các tuyến hoặc vùng địa lý có quan hệ hình học với một polygon.

Elasticsearch cung cấp **geo_shape query** để thực hiện những phép so sánh này. Query nhận một hình học truy vấn và một quan hệ không gian, sau đó so sánh nó với hình học được lập chỉ mục trong từng document.

Geo-shape query hỗ trợ các quan hệ:

- `INTERSECTS`: hai hình có ít nhất một điểm chung.
- `WITHIN`: hình trong document nằm hoàn toàn bên trong hình truy vấn.
- `CONTAINS`: hình trong document bao trọn hình truy vấn.
- `DISJOINT`: hai hình không có điểm chung.

Geo-shape query có thể tìm document được lập chỉ mục bằng field `geo_shape` hoặc `geo_point`. Nếu dữ liệu chỉ là tọa độ điểm, `geo_point` thường là mapping phù hợp hơn. Khi cần lưu đường, polygon hoặc các hình phức tạp, hãy dùng `geo_shape`.

## 2. Phân biệt geo_point, geo_shape và shape

Elasticsearch có các kiểu dữ liệu địa lý và hình học với mục đích khác nhau:

| Field type | Dữ liệu | Hệ tọa độ | Trường hợp sử dụng |
|---|---|---|---|
| `geo_point` | Một điểm địa lý | WGS-84 longitude/latitude | Vị trí cửa hàng, thiết bị, người dùng |
| `geo_shape` | Điểm, đường, polygon, multipolygon và các hình địa lý | WGS-84 longitude/latitude | Ranh giới khu vực, vùng phủ sóng, tuyến đường |
| `shape` | Hình học hai chiều X/Y | Hệ tọa độ phẳng Cartesian | Bản đồ nội bộ, sơ đồ mặt bằng, tọa độ không gian không phải địa lý |

`geo_shape` xử lý dữ liệu trên hệ tọa độ địa lý. `shape` xử lý tọa độ phẳng X/Y và không mang ý nghĩa kinh độ, vĩ độ. Không nên dùng `shape` cho ranh giới địa lý chỉ vì cả hai đều nhận GeoJSON hoặc WKT.

Nếu ứng dụng chỉ lưu vị trí của một cửa hàng, hãy cân nhắc `geo_point`. Nếu ứng dụng lưu ranh giới của khu vực cửa hàng phục vụ, hãy dùng `geo_shape`. Geo-shape query có thể truy vấn cả hai loại field, nhưng semantics của hình học vẫn phụ thuộc vào kiểu dữ liệu đã lập chỉ mục.

## 3. Khai báo mapping geo_shape

Elasticsearch yêu cầu khai báo rõ field kiểu `geo_shape` trong mapping.

Ví dụ tạo index `delivery-zones`:

~~~http
PUT /delivery-zones
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "boundary": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

Field `boundary` lưu hình học của vùng giao hàng. Field `name` lưu tên vùng.

Có thể khai báo thêm các tùy chọn cho geo_shape:

~~~json
{
  "boundary": {
    "type": "geo_shape",
    "orientation": "right",
    "ignore_malformed": false,
    "ignore_z_value": true,
    "coerce": false
  }
}
~~~

Một số tùy chọn quan trọng:

| Tùy chọn | Mục đích | Mặc định |
|---|---|---|
| `orientation` | Quy định hướng vòng polygon, chủ yếu quan trọng với WKT và polygon qua kinh tuyến 180° | `RIGHT` |
| `ignore_malformed` | Bỏ qua hình học sai định dạng thay vì từ chối document | `false` |
| `ignore_z_value` | Chấp nhận tọa độ ba chiều nhưng chỉ lập chỉ mục longitude/latitude | `true` |
| `coerce` | Tự đóng vòng polygon chưa khép kín | `false` |
| `index` | Bật hoặc tắt cấu trúc phục vụ tìm kiếm nhanh | `true` |
| `doc_values` | Lưu dữ liệu dạng columnar cho một số thao tác | `true` |

Không nên bật `ignore_malformed` hoặc `coerce` để che giấu lỗi dữ liệu địa lý. Nếu polygon sai tọa độ, sai thứ tự điểm hoặc tự cắt không hợp lệ, cần xử lý ở nguồn dữ liệu để bảo đảm ranh giới được lập chỉ mục đúng.

## 4. GeoJSON và WKT

Elasticsearch hỗ trợ hai cách biểu diễn hình học phổ biến:

- **GeoJSON:** cấu trúc JSON có `type` và `coordinates`.
- **WKT (Well-Known Text):** biểu diễn hình học bằng chuỗi văn bản.

Ví dụ một điểm:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

Dạng WKT tương ứng:

~~~text
POINT (106.7009 10.7769)
~~~

Ví dụ một đường:

~~~json
{
  "type": "LineString",
  "coordinates": [
    [106.7009, 10.7769],
    [106.7050, 10.7800],
    [106.7100, 10.7850]
  ]
}
~~~

WKT tương ứng:

~~~text
LINESTRING (106.7009 10.7769, 106.7050 10.7800, 106.7100 10.7850)
~~~

Các loại geometry thường được hỗ trợ:

| GeoJSON type | WKT type | Ý nghĩa |
|---|---|---|
| `Point` | `POINT` | Một điểm |
| `LineString` | `LINESTRING` | Đường gồm ít nhất hai điểm |
| `Polygon` | `POLYGON` | Vùng có biên khép kín |
| `MultiPoint` | `MULTIPOINT` | Nhiều điểm rời nhau |
| `MultiLineString` | `MULTILINESTRING` | Nhiều đường |
| `MultiPolygon` | `MULTIPOLYGON` | Nhiều polygon |
| `GeometryCollection` | `GEOMETRYCOLLECTION` | Tập hợp nhiều loại geometry |
| `Envelope` | `BBOX` | Hình chữ nhật bao |

Trong GeoJSON, `type` và `coordinates` là hai thành phần quan trọng để xác định hình học. `GeometryCollection` dùng `geometries` để chứa các geometry thành phần.

### Thứ tự tọa độ

Đây là lỗi thường gặp nhất khi làm việc với GeoJSON:

**Elasticsearch dùng thứ tự longitude, latitude (X, Y), không phải latitude, longitude.**

Ví dụ:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

- `106.7009` là longitude.
- `10.7769` là latitude.

Nhiều API bản đồ hoặc giao diện người dùng hiển thị tọa độ theo thứ tự latitude, longitude. Khi chuyển dữ liệu từ API đó sang GeoJSON, cần đảo đúng thứ tự. Nếu không, điểm có thể nằm ở vị trí hoàn toàn khác.

Elasticsearch sử dụng hệ tọa độ WGS-84 cho geo_shape. Không đưa tọa độ pixel, tọa độ bản vẽ hoặc tọa độ Cartesian tùy ý vào field này.

## 5. Polygon, vòng ngoài và lỗ bên trong

Polygon biểu diễn một vùng khép kín. Trong GeoJSON, tọa độ polygon là một mảng các vòng:

- Vòng đầu tiên là đường biên ngoài.
- Các vòng tiếp theo là lỗ nằm bên trong polygon.

Ví dụ polygon đơn giản:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.68, 10.75],
      [106.72, 10.75],
      [106.72, 10.79],
      [106.68, 10.79],
      [106.68, 10.75]
    ]
  ]
}
~~~

Điểm đầu và điểm cuối của vòng ngoài phải trùng nhau. Polygon có ít nhất ba cạnh nên vòng ngoài cần tối thiểu bốn tọa độ, tính cả điểm đóng vòng.

Polygon có lỗ bên trong:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.68, 10.75],
      [106.74, 10.75],
      [106.74, 10.81],
      [106.68, 10.81],
      [106.68, 10.75]
    ],
    [
      [106.70, 10.77],
      [106.72, 10.77],
      [106.72, 10.79],
      [106.70, 10.79],
      [106.70, 10.77]
    ]
  ]
}
~~~

Vòng thứ hai là một vùng rỗng. Điểm nằm trong lỗ không được xem là nằm trong phần diện tích của polygon.

Nếu một khu vực gồm nhiều vùng tách biệt, dùng `MultiPolygon`. Nếu một geometry cần chứa nhiều loại đối tượng, có thể dùng `GeometryCollection`.

## 6. Lưu hình học vào document

Sau khi mapping được tạo, có thể index document chứa polygon:

~~~http
PUT /delivery-zones/_doc/zone-01
{
  "name": "Central Zone",
  "boundary": {
    "type": "Polygon",
    "coordinates": [
      [
        [106.68, 10.75],
        [106.72, 10.75],
        [106.72, 10.79],
        [106.68, 10.79],
        [106.68, 10.75]
      ]
    ]
  }
}
~~~

Một document khác có thể lưu đường:

~~~http
PUT /delivery-zones/_doc/zone-02
{
  "name": "North Route",
  "boundary": {
    "type": "LineString",
    "coordinates": [
      [106.70, 10.78],
      [106.73, 10.80],
      [106.76, 10.82]
    ]
  }
}
~~~

Elasticsearch phân rã hình học thành cấu trúc không gian để phục vụ tìm kiếm. Với polygon và multipolygon, chi phí xử lý phụ thuộc đáng kể vào số lượng đỉnh. Một ranh giới có hàng trăm nghìn điểm sẽ tốn công xử lý và tài nguyên hơn một polygon đơn giản.

Nếu nguồn dữ liệu chứa quá nhiều điểm, hãy cân nhắc đơn giản hóa hình học trước khi index. Việc đơn giản hóa phải giữ được độ chính xác cần thiết của ranh giới nghiệp vụ.

## 7. Cấu trúc geo_shape query

Một geo_shape query cơ bản có dạng:

~~~json
{
  "query": {
    "geo_shape": {
      "boundary": {
        "shape": {
          "type": "Polygon",
          "coordinates": [
            [
              [106.69, 10.76],
              [106.71, 10.76],
              [106.71, 10.78],
              [106.69, 10.78],
              [106.69, 10.76]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

Các thành phần:

- `geo_shape`: loại query không gian.
- `boundary`: field geometry được lưu trong document.
- `shape`: hình học truy vấn được cung cấp trực tiếp.
- `relation`: quan hệ không gian cần kiểm tra.

Nếu không chỉ định `relation`, Elasticsearch dùng `INTERSECTS` làm mặc định.

Có thể đặt geo_shape query trong `bool.filter` khi chỉ muốn lọc document theo hình học:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "geo_shape": {
            "boundary": {
              "shape": {
                "type": "Polygon",
                "coordinates": [
                  [
                    [106.69, 10.76],
                    [106.71, 10.76],
                    [106.71, 10.78],
                    [106.69, 10.78],
                    [106.69, 10.76]
                  ]
                ]
              },
              "relation": "intersects"
            }
          }
        }
      ]
    }
  }
}
~~~

Ở đây, document phải vừa có `active = true` vừa đáp ứng quan hệ hình học. Dùng filter context phù hợp khi điều kiện địa lý chỉ quyết định document có được trả về hay không, không cần tính điểm liên quan.

## 8. Bốn quan hệ hình học

Phần quan trọng nhất của geo_shape query là hiểu đúng chiều so sánh. Elasticsearch so sánh:

- **Indexed geometry:** hình học được lưu trong field của document.
- **Query geometry:** hình học được gửi trong request tìm kiếm.

Các quan hệ được định nghĩa theo hình học trong document so với hình học truy vấn.

Giả sử hình truy vấn là một polygon khu vực lớn:

| Relation | Điều kiện trên geometry trong document | Ví dụ |
|---|---|---|
| `INTERSECTS` | Có ít nhất một điểm chung với query shape | Vùng giao hàng chạm hoặc cắt qua khu vực chọn |
| `WITHIN` | Nằm hoàn toàn bên trong query shape | Quận nằm trọn trong vùng tìm kiếm |
| `CONTAINS` | Bao trọn query shape | Khu vực dịch vụ bao phủ toàn bộ vùng người dùng vẽ |
| `DISJOINT` | Không có điểm chung với query shape | Khu vực hoàn toàn nằm ngoài vùng chọn |

### INTERSECTS

`INTERSECTS` là quan hệ mặc định. Hai hình được xem là giao nhau khi có ít nhất một điểm chung, kể cả điểm nằm trên đường biên.

Ví dụ tìm các vùng giao hàng có bất kỳ phần nào giao với khu vực người dùng chọn:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Polygon",
        "coordinates": [
          [
            [106.69, 10.76],
            [106.71, 10.76],
            [106.71, 10.78],
            [106.69, 10.78],
            [106.69, 10.76]
          ]
        ]
      },
      "relation": "intersects"
    }
  }
}
~~~

Một vùng giao hàng chỉ cần chạm vào biên hoặc nằm một phần trong polygon truy vấn là có thể được trả về.

Dùng `INTERSECTS` khi nghiệp vụ muốn tìm mọi đối tượng có liên quan đến khu vực đã chọn.

### WITHIN

`WITHIN` yêu cầu hình trong document nằm hoàn toàn bên trong hình truy vấn. Theo semantics hiện tại, phần nằm trên biên cũng được tính là nằm trong.

Ví dụ tìm những vùng giao hàng nằm trọn trong khu vực người dùng chọn:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Polygon",
        "coordinates": [
          [
            [106.69, 10.76],
            [106.75, 10.76],
            [106.75, 10.82],
            [106.69, 10.82],
            [106.69, 10.76]
          ]
        ]
      },
      "relation": "within"
    }
  }
}
~~~

Nếu vùng trong document vượt ra ngoài query polygon dù chỉ một phần, nó không đáp ứng quan hệ `WITHIN`.

Quan hệ `WITHIN` không hỗ trợ line geometries theo tài liệu Elasticsearch. Khi làm việc với đường, cần kiểm tra loại geometry và chọn quan hệ khác phù hợp.

### CONTAINS

`CONTAINS` đảo chiều so với `WITHIN`: hình trong document phải bao trọn hình truy vấn.

Ví dụ tìm vùng dịch vụ có thể bao phủ toàn bộ khu vực mà người dùng vẽ:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Polygon",
        "coordinates": [
          [
            [106.70, 10.77],
            [106.71, 10.77],
            [106.71, 10.78],
            [106.70, 10.78],
            [106.70, 10.77]
          ]
        ]
      },
      "relation": "contains"
    }
  }
}
~~~

Ở đây, polygon được lưu trong document phải bao trọn polygon truy vấn. Nếu chỉ giao nhau một phần, document không được trả về theo `CONTAINS`.

### DISJOINT

`DISJOINT` yêu cầu hai hình không có bất kỳ điểm chung nào. Đây là phép phủ định của `INTERSECTS`.

Ví dụ tìm các khu vực hoàn toàn không giao với vùng hạn chế:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Polygon",
        "coordinates": [
          [
            [106.69, 10.76],
            [106.71, 10.76],
            [106.71, 10.78],
            [106.69, 10.78],
            [106.69, 10.76]
          ]
        ]
      },
      "relation": "disjoint"
    }
  }
}
~~~

`DISJOINT` có thể trả về một lượng lớn document vì hầu hết hình học nằm ngoài khu vực truy vấn. Hãy kết hợp thêm các điều kiện nghiệp vụ hoặc giới hạn tập dữ liệu trước khi sử dụng trong một truy vấn rộng.

## 9. Tránh nhầm chiều WITHIN và CONTAINS

Hai relation này dễ bị nhầm vì ngôn ngữ tự nhiên có thể diễn đạt cùng một yêu cầu theo hai phía.

Ví dụ:

- Query shape là vùng thành phố.
- Document shape là một quận.

Nếu muốn tìm các quận nằm trong thành phố, dùng `WITHIN` vì hình trong document nằm trong hình truy vấn.

Nếu muốn tìm một thành phố bao trọn khu vực quận được gửi lên, dùng `CONTAINS` vì hình trong document chứa hình truy vấn.

Sơ đồ:

~~~text
WITHIN
Query shape:       +-------------------------+
Document shape:          +-------------+
                         |             |
                         +-------------+

Document nằm trong Query.


CONTAINS
Document shape:    +-------------------------+
Query shape:              +-------------+
                           |           |
                           +-------------+

Document bao trọn Query.
~~~

Hãy xác định rõ hình nào nằm trong index và hình nào được gửi trong query trước khi chọn relation. Không nên suy luận relation chỉ từ câu tiếng Việt “tìm khu vực chứa trong” mà không xác định chủ thể của từng hình.

## 10. Inline shape và indexed_shape

Geo-shape query hỗ trợ hai cách cung cấp hình truy vấn:

1. `shape`: truyền trực tiếp GeoJSON hoặc WKT trong query.
2. `indexed_shape`: tham chiếu một hình đã được lưu trong document của một index khác.

### Inline shape

Inline shape phù hợp khi hình truy vấn được người dùng vẽ hoặc tạo động:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Envelope",
        "coordinates": [
          [106.68, 10.80],
          [106.75, 10.74]
        ]
      },
      "relation": "intersects"
    }
  }
}
~~~

`Envelope` là hình chữ nhật bao, được xác định bằng góc trên bên trái và góc dưới bên phải. Với GeoJSON envelope, thứ tự là:

`[[minLon, maxLat], [maxLon, minLat]]`.

### Indexed shape

Nếu ứng dụng thường xuyên dùng cùng một vùng địa lý, có thể lưu shape đó ở index riêng:

~~~http
PUT /search-shapes
{
  "mappings": {
    "properties": {
      "geometry": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

Lưu một hình có ID cố định:

~~~http
PUT /search-shapes/_doc/central-region
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [106.68, 10.75],
        [106.74, 10.75],
        [106.74, 10.81],
        [106.68, 10.81],
        [106.68, 10.75]
      ]
    ]
  }
}
~~~

Sau đó tham chiếu hình đã lưu:

~~~json
{
  "query": {
    "geo_shape": {
      "boundary": {
        "indexed_shape": {
          "index": "search-shapes",
          "id": "central-region",
          "path": "geometry"
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

Các thuộc tính quan trọng của `indexed_shape`:

| Thuộc tính | Ý nghĩa |
|---|---|
| `index` | Index chứa document có geometry; mặc định là `shapes` |
| `id` | ID document chứa geometry |
| `path` | Field chứa geometry; mặc định là `shape` |
| `routing` | Routing của document hình học nếu index yêu cầu |

Indexed shape hữu ích khi nhiều truy vấn dùng chung một ranh giới, chẳng hạn vùng hành chính, vùng cấm hoặc vùng phủ dịch vụ. Khi ranh giới thay đổi, ứng dụng cập nhật document shape tại index nguồn và các query sau có thể tham chiếu lại ID đó.

## 11. ignore_unmapped khi tìm trên nhiều index

Khi tìm kiếm nhiều index có mapping khác nhau, có thể có index không khai báo field geometry. Mặc định, geo_shape query trên field không được mapping sẽ phát sinh lỗi.

Có thể dùng `ignore_unmapped`:

~~~json
{
  "query": {
    "geo_shape": {
      "boundary": {
        "shape": {
          "type": "Point",
          "coordinates": [106.70, 10.77]
        },
        "relation": "intersects"
      },
      "ignore_unmapped": true
    }
  }
}
~~~

Khi `ignore_unmapped: true`, Elasticsearch bỏ qua index không có field đó và không match document nào từ index thiếu mapping. Điều này hữu ích khi query một alias hoặc nhiều index có schema không đồng nhất.

Tùy chọn này không sửa mapping và không biến field thiếu thành geo_shape. Nếu field phải tồn tại trong mọi index, hãy chuẩn hóa mapping thay vì dựa vào `ignore_unmapped`.

## 12. Geo-shape query trên geo_point

Geo-shape query cũng có thể tìm document có field `geo_point` bằng cách so sánh điểm với hình truy vấn.

Ví dụ mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "name": "Store A",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Tìm các điểm cửa hàng giao với polygon:

~~~json
{
  "query": {
    "geo_shape": {
      "location": {
        "shape": {
          "type": "Polygon",
          "coordinates": [
            [
              [106.68, 10.75],
              [106.72, 10.75],
              [106.72, 10.79],
              [106.68, 10.79],
              [106.68, 10.75]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

Với điểm, `INTERSECTS` có nghĩa điểm nằm trong hoặc trên biên của query geometry. `WITHIN` cũng có thể dùng để yêu cầu điểm nằm trong hình truy vấn. Không nên dùng `CONTAINS` cho một điểm để diễn đạt rằng polygon truy vấn chứa điểm; chiều relation luôn được hiểu từ indexed geometry của document so với query geometry.

## 13. Spring Data Elasticsearch hỗ trợ GeoJSON như thế nào?

Spring Data Elasticsearch có các kiểu GeoJSON trong package:

`org.springframework.data.elasticsearch.core.geo`

Một số lớp được hỗ trợ:

- `GeoJsonPoint`.
- `GeoJsonMultiPoint`.
- `GeoJsonLineString`.
- `GeoJsonMultiLineString`.
- `GeoJsonPolygon`.
- `GeoJsonMultiPolygon`.
- `GeoJsonGeometryCollection`.

Các kiểu GeoJSON này được ánh xạ sang cấu trúc document theo đặc tả GeoJSON. Khi Spring Data ghi mapping cho entity có property GeoJSON, property tương ứng được khai báo thành field `geo_shape`.

Ví dụ entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.geo.GeoJsonPolygon;

@Document(indexName = "delivery-zones")
public class DeliveryZone {

    @Id
    private String id;

    private String name;

    private GeoJsonPolygon boundary;

    // Constructors, getters và setters
}
~~~

`GeoJsonPolygon` biểu diễn ranh giới vùng giao hàng. Nếu property là `GeoJsonPoint`, `GeoJsonLineString` hoặc các loại GeoJSON khác, Spring Data cũng hỗ trợ mapping tương ứng.

Spring Data có thể dùng `ElasticsearchOperations` để index và tìm kiếm entity. Khi cần truy vấn geo_shape phức tạp, `NativeQuery` là lựa chọn phù hợp vì nó cho phép dùng các query builder của Elasticsearch Java API Client.

## 14. Xây dựng geo_shape query bằng NativeQuery

`NativeQuery` sử dụng các kiểu query của Elasticsearch Java API Client. Với geo_shape, có thể dùng builder `geoShape` và enum `GeoShapeRelation`.

Ví dụ query tìm các vùng giao hàng giao với một polygon:

~~~java
import co.elastic.clients.elasticsearch._types.GeoShapeRelation;
import co.elastic.clients.json.JsonData;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;

String polygonJson = """
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.69, 10.76],
      [106.71, 10.76],
      [106.71, 10.78],
      [106.69, 10.78],
      [106.69, 10.76]
    ]
  ]
}
""";

Query query = NativeQuery.builder()
    .withQuery(q -> q
        .geoShape(gs -> gs
            .field("boundary")
            .shape(s -> s
                .shape(JsonData.fromJson(polygonJson))
                .relation(GeoShapeRelation.Intersects)
            )
        )
    )
    .build();

SearchHits<DeliveryZone> hits = operations.search(
    query,
    DeliveryZone.class
);
~~~

Các thành phần:

- `NativeQuery.builder()` tạo query builder của Spring Data.
- `withQuery` nhận một Elasticsearch Java API Client query.
- `geoShape` tạo geo_shape query.
- `field("boundary")` chỉ định field geometry trong document.
- `JsonData.fromJson` chuyển chuỗi GeoJSON thành dữ liệu JSON cho Java API Client.
- `GeoShapeRelation.Intersects` chỉ định quan hệ giao nhau.
- `operations.search` thực thi query và ánh xạ kết quả thành entity.

Có thể thay enum relation:

~~~java
GeoShapeRelation.Intersects
GeoShapeRelation.Within
GeoShapeRelation.Contains
GeoShapeRelation.Disjoint
~~~

Tên enum trong Java API Client dùng PascalCase. Trong JSON Query DSL, giá trị relation được serialize thành chuỗi chữ thường tương ứng.

API builder cụ thể phụ thuộc phiên bản Elasticsearch Java API Client đi cùng Spring Data Elasticsearch. Hãy dùng dependency tương thích với phiên bản Spring Data của dự án.

## 15. Kết hợp geo_shape với các điều kiện nghiệp vụ

Trong thực tế, query địa lý thường đi cùng điều kiện khác như trạng thái hoạt động, loại dịch vụ hoặc quyền truy cập.

Ví dụ tìm vùng giao hàng active giao với polygon người dùng chọn:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .filter(f -> f
                .term(t -> t
                    .field("active")
                    .value(true)
                )
            )
            .filter(f -> f
                .geoShape(gs -> gs
                    .field("boundary")
                    .shape(s -> s
                        .shape(JsonData.fromJson(polygonJson))
                        .relation(GeoShapeRelation.Intersects)
                    )
                )
            )
        )
    )
    .build();

SearchHits<DeliveryZone> hits = operations.search(
    query,
    DeliveryZone.class
);
~~~

Trong ví dụ:

- Term query giới hạn document có `active = true`.
- Geo-shape query giới hạn document có boundary giao với polygon.
- Bool filter yêu cầu cả hai điều kiện cùng đúng.

Nếu query được tạo động từ dữ liệu người dùng, hãy kiểm tra GeoJSON đầu vào trước khi gửi tới Elasticsearch. Không nên nhận một chuỗi JSON bất kỳ rồi cho rằng nó là polygon hợp lệ.

## 16. Tạo polygon bằng GeoJsonPolygon trong Spring Data

Nếu ứng dụng muốn tạo geometry bằng Java object thay vì giữ chuỗi JSON, Spring Data cung cấp `GeoJsonPolygon`.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.geo.GeoJsonPolygon;

GeoJsonPolygon polygon = GeoJsonPolygon.ofGeoPoints(
    List.of(
        new GeoPoint(10.76, 106.69),
        new GeoPoint(10.76, 106.71),
        new GeoPoint(10.78, 106.71),
        new GeoPoint(10.78, 106.69),
        new GeoPoint(10.76, 106.69)
    )
);
~~~

`GeoPoint` trong Spring Data nhận latitude và longitude theo thứ tự constructor của kiểu này. Khi được chuyển thành GeoJSON, tọa độ sẽ được serialize theo thứ tự longitude, latitude.

Điểm đầu và điểm cuối phải trùng nhau để polygon khép kín. Ví dụ trên dùng cùng tọa độ đầu/cuối.

`GeoJsonPolygon` hữu ích khi ứng dụng muốn dùng kiểu Java rõ ràng trong entity hoặc trong logic tạo geometry. Khi chuyển object thành query shape cho Java API Client, vẫn cần đưa dữ liệu vào đúng dạng `JsonData` hoặc dùng cơ chế serialize phù hợp.

## 17. Quan hệ hình học không đồng nghĩa với khoảng cách

Geo-shape query trả lời câu hỏi về topology: hai hình giao nhau, chứa nhau, nằm trong nhau hay tách rời. Nó không trực tiếp tính khoảng cách theo mét giữa hai điểm hoặc hai vùng.

Chọn query theo yêu cầu:

| Nhu cầu | Query phù hợp |
|---|---|
| Tìm document có hình giao với polygon | `geo_shape` với `INTERSECTS` |
| Tìm hình nằm trọn trong polygon | `geo_shape` với `WITHIN` |
| Tìm hình bao trọn polygon truy vấn | `geo_shape` với `CONTAINS` |
| Tìm hình không giao với polygon | `geo_shape` với `DISJOINT` |
| Tìm điểm trong bán kính quanh tâm | `geo_distance` |
| Tìm điểm/hình giao với hình chữ nhật | `geo_bounding_box` hoặc `geo_shape` với envelope |
| Tìm hình giao với geohash hoặc tile | `geo_grid` |

Các quan hệ `WITHIN` và `CONTAINS` được đánh giá trong không gian longitude/latitude hai chiều theo implementation của Lucene. Chúng không phải phép đo khoảng cách địa cầu theo cung tròn lớn (great-circle) hoặc phép tính geodesic trên ellipsoid.

Nếu nghiệp vụ cần khoảng cách thực tế trên bề mặt Trái Đất, ví dụ cửa hàng trong bán kính 5 km, hãy dùng `geo_distance` query. Không thay thế distance query bằng polygon lớn xấp xỉ nếu cần kết quả theo mét chính xác.

## 18. Orientation và kinh tuyến quốc tế

Polygon có hướng của vòng tọa độ:

- `RIGHT`: ngược chiều kim đồng hồ.
- `LEFT`: cùng chiều kim đồng hồ.

Elasticsearch dùng orientation để xác định polygon có đi qua kinh tuyến quốc tế ở longitude ±180° hay không.

Với GeoJSON, mặc định outer ring theo hướng ngược chiều kim đồng hồ và inner ring theo chiều kim đồng hồ. Đây là quy ước của GeoJSON. Với WKT, mapping có thể đặt orientation mặc định vì WKT không bắt buộc một thứ tự đỉnh cụ thể.

Khi polygon có chênh lệch longitude nhỏ hơn 180°, orientation không ảnh hưởng cách xác định polygon qua dateline. Khi phạm vi longitude đạt từ 180° trở lên, orientation có thể quyết định cách Elasticsearch hiểu và chia polygon qua dateline.

Nếu ứng dụng xử lý dữ liệu toàn cầu, cần kiểm tra orientation của polygon và cách biểu diễn vùng đi qua kinh tuyến ±180°. Không nên đảo thứ tự tọa độ tùy tiện để sửa một polygon có vẻ bị ngược.

## 19. Ý nghĩa hình học và giới hạn semantics

Các quan hệ không gian trong Elasticsearch được thực hiện bằng geometry hai chiều. Với `geo_shape`, tọa độ là longitude/latitude WGS-84 nhưng các predicate không phải phép kiểm tra geodesic trên bề mặt ellipsoid.

Điều này có một số hệ quả:

- Với vùng nhỏ ở vĩ độ thấp, kết quả thường phù hợp với kỳ vọng của ứng dụng bản đồ thông thường.
- Với vùng rất lớn hoặc gần cực, cách tính phẳng hai chiều có thể khác phép tính địa cầu.
- Query shape được lượng tử hóa để khớp độ chính xác của dữ liệu đã lập chỉ mục.
- Hình đã index được tessellate thành các thành phần tam giác; phép so sánh không phải so chuỗi GeoJSON nguyên văn.
- Quan hệ WITHIN/CONTAINS có tên tương tự các predicate GIS phổ biến nhưng không bảo đảm mọi chi tiết theo OGC Simple Features hoặc DE-9IM.

Nếu nghiệp vụ pháp lý, địa chính hoặc quy hoạch cần tuân thủ nghiêm ngặt một chuẩn GIS cụ thể, hãy xác nhận semantics bằng bộ dữ liệu kiểm thử đại diện và thư viện GIS chuyên dụng trước khi dùng kết quả làm căn cứ cuối cùng.

## 20. Kiểm tra dữ liệu hình học trước khi index

Dữ liệu geometry sai có thể khiến thao tác index bị từ chối hoặc cho kết quả tìm kiếm ngoài dự kiến. Một số kiểm tra nên thực hiện tại tầng ingest:

**Kiểm tra thứ tự tọa độ.** GeoJSON phải dùng longitude rồi latitude.

**Kiểm tra phạm vi.** Longitude thường nằm trong khoảng -180 đến 180; latitude nằm trong khoảng -90 đến 90.

**Kiểm tra polygon khép kín.** Điểm đầu và điểm cuối của mỗi ring phải trùng nhau.

**Kiểm tra số điểm.** Polygon phải có tối thiểu bốn tọa độ cho ring khép kín.

**Kiểm tra holes.** Các ring bên trong phải nằm trong outer ring và không được diễn giải nhầm thành phần diện tích.

**Kiểm tra orientation.** Đặc biệt với WKT và polygon qua dateline.

**Kiểm tra hình tự cắt.** Polygon tự giao nhau có thể không hợp lệ hoặc không mang semantics mà nghiệp vụ mong muốn.

**Kiểm tra độ phức tạp.** Polygon quá nhiều đỉnh làm tăng chi phí tessellation và tìm kiếm.

Có thể dùng `ignore_malformed` hoặc `coerce` cho một số tình huống nhập dữ liệu, nhưng không nên xem chúng là giải pháp thay thế validation. Một geometry bị bỏ qua không thể tham gia query như ứng dụng mong đợi.

## 21. Hiệu năng và lựa chọn cách truy vấn

Geo-shape query có chi phí phụ thuộc vào số lượng document, số lượng đỉnh, độ phức tạp của polygon và số shard liên quan.

Một số nguyên tắc thực tế:

- Dùng `geo_point` cho dữ liệu chỉ có điểm.
- Dùng `geo_shape` khi cần lưu đường, polygon hoặc hình phức tạp.
- Giảm số đỉnh không cần thiết nhưng giữ độ chính xác nghiệp vụ.
- Tái sử dụng `indexed_shape` cho những hình truy vấn cố định được dùng nhiều lần.
- Kết hợp geo_shape với các filter khác để giảm phạm vi document.
- Dùng `geo_distance` nếu chỉ cần bán kính quanh một điểm.
- Dùng `geo_bounding_box` nếu chỉ cần hình chữ nhật bao đơn giản.
- Tránh query `DISJOINT` trên tập document quá rộng nếu không cần thiết.
- Theo dõi latency và kích thước request geometry trên dữ liệu thật.

Khi query một polygon rất phức tạp, truyền inline shape ở mỗi request làm tăng payload. Nếu hình đó được dùng lại nhiều lần, lưu nó ở index riêng và dùng indexed shape có thể làm request ngắn gọn hơn.

## 22. Những lỗi thường gặp

**Đảo latitude và longitude.** Elasticsearch cần GeoJSON theo longitude, latitude. Sai thứ tự khiến shape nằm sai vị trí.

**Dùng geo_point cho polygon.** geo_point chỉ biểu diễn điểm. Ranh giới và vùng cần field geo_shape.

**Dùng shape thay cho geo_shape.** shape dùng hệ tọa độ Cartesian X/Y; geo_shape dùng tọa độ địa lý WGS-84.

**Quên đóng polygon.** Điểm đầu và cuối ring phải trùng nhau. Nếu không, document có thể bị từ chối khi index.

**Nhầm chiều WITHIN và CONTAINS.** Relation luôn so sánh indexed geometry trong document với query geometry. Hãy xác định rõ hình nào được lưu và hình nào được gửi.

**Cho rằng INTERSECTS chỉ cần nằm bên trong.** Chỉ cần hai hình có một điểm chung, kể cả chạm biên, là có thể giao nhau.

**Dùng geo_shape để tính bán kính.** Relation không đo khoảng cách theo mét. Dùng geo_distance khi nghiệp vụ yêu cầu khoảng cách.

**Nhầm GeoJSON với WKT orientation.** GeoJSON có quy tắc orientation mặc định riêng; WKT cần chú ý mapping orientation.

**Đưa polygon quá nhiều đỉnh.** Tessellation có thể tốn tài nguyên. Đơn giản hóa geometry có kiểm soát trước khi index.

**Dùng indexed_shape sai path hoặc ID.** Kiểm tra index, document ID, routing và field path chứa geometry.

**Bỏ qua mapping không đồng nhất.** Khi tìm trên nhiều index, field thiếu mapping có thể làm query lỗi. Dùng ignore_unmapped khi semantics phù hợp hoặc chuẩn hóa mapping.

**Coi kết quả như chuẩn GIS tuyệt đối.** Elasticsearch dùng phép toán không gian hai chiều trên longitude/latitude. Với nghiệp vụ cần chuẩn GIS nghiêm ngặt, hãy xác minh semantics.

## 23. Quy trình triển khai geo_shape query

Có thể triển khai theo các bước sau:

1. Xác định dữ liệu chỉ là điểm hay có đường, polygon và vùng.
2. Chọn `geo_point` hoặc `geo_shape` đúng với loại dữ liệu.
3. Khai báo mapping rõ ràng trước khi index document.
4. Chuẩn hóa nguồn tọa độ thành longitude, latitude.
5. Kiểm tra GeoJSON/WKT, ring closure, orientation và phạm vi tọa độ.
6. Index geometry vào document.
7. Xác định hình truy vấn sẽ được gửi inline hay lưu thành indexed shape.
8. Chọn relation theo chiều indexed geometry và query geometry.
9. Kết hợp query với bool filter nếu có điều kiện nghiệp vụ khác.
10. Thực thi bằng REST API, StringQuery hoặc NativeQuery.
11. Kiểm tra kết quả với các tình huống giao biên, nằm trong, bao chứa và không giao.
12. Đánh giá hiệu năng với polygon có độ phức tạp gần dữ liệu production.
13. Theo dõi lỗi mapping, geometry malformed và thời gian thực thi.

## Kết luận

Geo-shape query cho phép tìm document theo quan hệ hình học giữa geometry được lưu và geometry truy vấn. Bốn quan hệ chính là `INTERSECTS`, `WITHIN`, `CONTAINS` và `DISJOINT`. Cần hiểu rõ chiều so sánh: Elasticsearch luôn xét hình trong document so với hình được gửi trong query.

Để sử dụng đúng, hãy khai báo field `geo_shape`, biểu diễn geometry bằng GeoJSON hoặc WKT, giữ thứ tự longitude/latitude và bảo đảm polygon được khép kín. Hình truy vấn có thể được truyền trực tiếp bằng `shape` hoặc tái sử dụng từ index khác qua `indexed_shape`.

Trong Spring Data Elasticsearch, các kiểu `GeoJsonPoint`, `GeoJsonLineString`, `GeoJsonPolygon` và những GeoJSON implementation khác hỗ trợ mapping hình học. Với query phức tạp, `NativeQuery` cho phép xây dựng geo_shape query bằng Elasticsearch Java API Client. Nếu cần khoảng cách theo mét, hãy dùng `geo_distance`; nếu cần phép toán GIS theo chuẩn nghiêm ngặt, hãy xác minh semantics bằng dữ liệu kiểm thử chuyên biệt.

## Tài liệu tham khảo

- [Elasticsearch — Geo-shape field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-shape)
- [Elasticsearch — Geo-shape query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-geo-shape-query)
- [Elasticsearch — Geo queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/geo-queries)
- [Elasticsearch — Shape field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/shape)
- [Spring Data Elasticsearch — Object Mapping and GeoJSON Types](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Elasticsearch Operations and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — GeoJsonPolygon API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/geo/GeoJsonPolygon.html)
- [Elasticsearch Java API Client — GeoShapeFieldQuery.Builder](https://artifacts.elastic.co/javadoc/co/elastic/clients/elasticsearch-java/8.18.8/co/elastic/clients/elasticsearch/_types/query_dsl/GeoShapeFieldQuery.Builder.html)
- [Elasticsearch Java API Client — GeoShapeRelation](https://artifacts.elastic.co/javadoc/co/elastic/clients/elasticsearch-java/8.17.3/co/elastic/clients/elasticsearch/_types/GeoShapeRelation.html)
